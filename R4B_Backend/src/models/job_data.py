"""Data models for job data processing."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field, validator
import re


class ExperienceLevel(str, Enum):
    """Experience level categories."""
    ENTRY_LEVEL = "entry_level"
    MID_LEVEL = "mid_level"
    SENIOR_LEVEL = "senior_level"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class SalaryType(str, Enum):
    """Salary type categories."""
    HOURLY = "hourly"
    ANNUAL = "annual"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    UNKNOWN = "unknown"


class JobQuery(BaseModel):
    """Model for user job search query."""
    
    job_title: str = Field(..., min_length=1, max_length=200, description="Job title to search for")
    location: str = Field(..., min_length=1, max_length=200, description="Location to search in")
    max_results: int = Field(default=50, ge=1, le=1000, description="Maximum number of results to return")
    
    @validator("job_title", "location")
    def validate_text_fields(cls, v):
        """Validate and clean text fields."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class SalaryInfo(BaseModel):
    """Model for salary information."""
    
    min_salary: Optional[float] = Field(None, ge=0, description="Minimum salary")
    max_salary: Optional[float] = Field(None, ge=0, description="Maximum salary")
    salary_type: SalaryType = Field(default=SalaryType.UNKNOWN, description="Type of salary")
    currency: str = Field(default="USD", description="Currency code")
    raw_salary_text: Optional[str] = Field(None, description="Original salary text from source")
    
    @validator("max_salary")
    def validate_salary_range(cls, v, values):
        """Ensure max salary is greater than min salary."""
        min_sal = values.get("min_salary")
        if v is not None and min_sal is not None and v < min_sal:
            raise ValueError("Maximum salary must be greater than minimum salary")
        return v
    
    @property
    def average_salary(self) -> Optional[float]:
        """Calculate average salary if both min and max are available."""
        if self.min_salary is not None and self.max_salary is not None:
            return (self.min_salary + self.max_salary) / 2
        return self.min_salary or self.max_salary
    
    @property
    def salary_range_text(self) -> str:
        """Get formatted salary range text."""
        if self.min_salary is not None and self.max_salary is not None:
            return f"{self.currency} {self.min_salary:,.0f} - {self.max_salary:,.0f} ({self.salary_type.value})"
        elif self.min_salary is not None:
            return f"{self.currency} {self.min_salary:,.0f}+ ({self.salary_type.value})"
        elif self.max_salary is not None:
            return f"{self.currency} {self.max_salary:,.0f} ({self.salary_type.value})"
        return "Salary not specified"


class JobData(BaseModel):
    """Model for individual job data."""
    
    job_id: Optional[str] = Field(None, description="Unique job identifier")
    job_title: str = Field(..., description="Job title")
    company: Optional[str] = Field(None, description="Company name")
    location: str = Field(..., description="Job location")
    salary_info: Optional[SalaryInfo] = Field(None, description="Salary information")
    experience_level: ExperienceLevel = Field(default=ExperienceLevel.UNKNOWN, description="Required experience level")
    job_description: Optional[str] = Field(None, description="Job description")
    job_url: Optional[str] = Field(None, description="URL to job posting")
    posted_date: Optional[datetime] = Field(None, description="Job posting date")
    scraped_at: datetime = Field(default_factory=datetime.now, description="When this data was scraped")
    source: str = Field(default="indeed", description="Data source")
    raw_data: Optional[Dict] = Field(None, description="Raw scraped data")
    
    @validator("job_title", "location")
    def validate_required_fields(cls, v):
        """Validate required fields."""
        if not v or not v.strip():
            raise ValueError("Required field cannot be empty")
        return v.strip()
    
    def extract_experience_level(self) -> ExperienceLevel:
        """Extract experience level from job title and description."""
        text = f"{self.job_title} {self.job_description or ''}".lower()
        
        # Define patterns for experience levels
        patterns = {
            ExperienceLevel.ENTRY_LEVEL: [
                r'\b(entry.?level|junior|intern|trainee|graduate|fresher|beginner)\b',
                r'\b(0.?1|0.?2)\s*years?\b',
                r'\bnew.?grad\b'
            ],
            ExperienceLevel.MID_LEVEL: [
                r'\b(mid.?level|intermediate|experienced|professional)\b',
                r'\b(2.?5|3.?5|3.?7)\s*years?\b'
            ],
            ExperienceLevel.SENIOR_LEVEL: [
                r'\b(senior|lead|principal|architect|expert)\b',
                r'\b(5\+|7\+|8\+|10\+)\s*years?\b',
                r'\b(5.?10|7.?12)\s*years?\b'
            ],
            ExperienceLevel.EXECUTIVE: [
                r'\b(director|manager|head|chief|vp|vice.?president|c.?level)\b',
                r'\b(10\+|15\+)\s*years?\b'
            ]
        }
        
        for level, level_patterns in patterns.items():
            for pattern in level_patterns:
                if re.search(pattern, text):
                    return level
        
        return ExperienceLevel.UNKNOWN


class JobDataCollection(BaseModel):
    """Model for a collection of job data."""
    
    query: JobQuery = Field(..., description="Original search query")
    jobs: List[JobData] = Field(default_factory=list, description="List of job data")
    total_found: int = Field(default=0, description="Total number of jobs found")
    scraped_count: int = Field(default=0, description="Number of jobs actually scraped")
    created_at: datetime = Field(default_factory=datetime.now, description="When this collection was created")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    
    @validator("scraped_count", pre=True, always=True)
    def set_scraped_count(cls, v, values):
        """Set scraped count based on jobs list length."""
        jobs = values.get("jobs", [])
        return len(jobs) if jobs else v
    
    def get_jobs_by_experience(self) -> Dict[ExperienceLevel, List[JobData]]:
        """Group jobs by experience level."""
        grouped = {}
        for job in self.jobs:
            level = job.experience_level
            if level not in grouped:
                grouped[level] = []
            grouped[level].append(job)
        return grouped
    
    def get_salary_statistics(self) -> Dict[str, Union[float, int]]:
        """Calculate salary statistics."""
        salaries = []
        for job in self.jobs:
            if job.salary_info and job.salary_info.average_salary:
                salaries.append(job.salary_info.average_salary)
        
        if not salaries:
            return {"count": 0}
        
        salaries.sort()
        count = len(salaries)
        
        return {
            "count": count,
            "min": min(salaries),
            "max": max(salaries),
            "average": sum(salaries) / count,
            "median": salaries[count // 2] if count % 2 == 1 else (salaries[count // 2 - 1] + salaries[count // 2]) / 2
        }


