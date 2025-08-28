import logging
from typing import Dict, Any, List, Optional
import re

logger = logging.getLogger(__name__)

class JobStructurer:
    """Structures job data to match the PDF table format"""
    
    def __init__(self):
        # Experience level definitions based on PDF
        self.experience_levels = {
            "level1": "No experience at all",
            "level2": "Recent graduate from technical school, no field experience, EPA cert",
            "level3": "1‐2 years experience in the field, NATE core cert",
            "level4": "3‐5 years in the field, passed a NATE specialty exam",
            "level5": "5+ years in the field, passed 3 NATE specialty exams"
        }
    
    def _extract_salary_range(self, salary_text: str) -> Dict[str, Optional[float]]:
        """Extract min and max salary from Indeed salary text"""
        if not salary_text:
            return {"min": None, "max": None, "currency": "USD", "period": "hour"}
        
        # Remove common text and extract numbers
        salary_text = salary_text.lower().strip()
        
        # Extract currency
        currency = "USD"
        if "€" in salary_text or "euro" in salary_text:
            currency = "EUR"
        elif "£" in salary_text or "pound" in salary_text:
            currency = "GBP"
        
        # Extract period
        period = "hour"
        if "year" in salary_text or "annum" in salary_text or "annual" in salary_text:
            period = "year"
        elif "month" in salary_text:
            period = "month"
        
        # Extract numbers using regex
        numbers = re.findall(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', salary_text)
        
        if len(numbers) >= 2:
            # Convert to float, removing commas
            min_salary = float(numbers[0].replace(',', ''))
            max_salary = float(numbers[1].replace(',', ''))
            return {
                "min": min_salary,
                "max": max_salary,
                "currency": currency,
                "period": period
            }
        elif len(numbers) == 1:
            # Single salary value
            salary = float(numbers[0].replace(',', ''))
            return {
                "min": salary,
                "max": salary,
                "currency": currency,
                "period": period
            }
        
        return {"min": None, "max": None, "currency": currency, "period": period}
    
    def _determine_experience_level(self, experience_text: str) -> str:
        """Determine experience level based on Indeed experience text"""
        if not experience_text:
            return "level1"  # Default to level1 if no experience text
        
        experience_text = experience_text.lower().strip()
        
        # Extract years using regex - handle ranges like "3-5 years" or "7+ years"
        range_match = re.search(r'(\d+)\s*-\s*(\d+)\s*years?', experience_text)
        if range_match:
            min_years = int(range_match.group(1))
            max_years = int(range_match.group(2))
            avg_years = (min_years + max_years) / 2
            
            if avg_years == 0:
                return "level1"
            elif avg_years <= 1.5:  # 1-2 years average
                return "level3"
            elif avg_years <= 4:    # 3-5 years average
                return "level4"
            else:                    # 5+ years
                return "level5"
        
        # Handle single year with + (e.g., "7+ years")
        single_match = re.search(r'(\d+)\+\s*years?', experience_text)
        if single_match:
            years = int(single_match.group(1))
            if years == 0:
                return "level1"
            elif years <= 2:
                return "level3"
            elif years <= 5:
                return "level4"
            else:  # 5+ years
                return "level5"
        
        # Handle single year (e.g., "5 years")
        single_year_match = re.search(r'(\d+)\s*years?', experience_text)
        if single_year_match:
            years = int(single_year_match.group(1))
            if years == 0:
                return "level1"
            elif years <= 2:
                return "level3"
            elif years <= 5:
                return "level4"
            else:  # 5+ years
                return "level5"
        
        # Fallback based on keywords
        if any(word in experience_text for word in ["entry", "junior", "associate", "no experience", "fresh graduate"]):
            return "level1"
        elif any(word in experience_text for word in ["graduate", "technical school", "epa cert"]):
            return "level2"
        elif any(word in experience_text for word in ["nate core", "1-2 years", "beginner"]):
            return "level3"
        elif any(word in experience_text for word in ["mid", "intermediate", "3-5 years", "nate specialty"]):
            return "level4"
        elif any(word in experience_text for word in ["senior", "lead", "expert", "5+ years", "principal", "architect"]):
            return "level5"
        
        return "level1"  # Default to level1 if no specific match
    
    def _convert_salary_to_annual(self, salary: float, period: str) -> float:
        """Convert salary to annual equivalent"""
        if period == "hour":
            return salary * 40 * 52  # 40 hours/week * 52 weeks
        elif period == "month":
            return salary * 12
        elif period == "year":
            return salary
        else:
            return salary
    
    def structure_job_data(self, scraped_jobs: List[Dict], bls_result: Dict, salary_result: Dict = None) -> Dict[str, Any]:
        """Structure job data to match PDF table format with BLS and salary.com data"""
        logger.info("🔧 [JobStructurer] Structuring %d jobs with BLS and salary.com data", len(scraped_jobs))
        
        try:
            # Extract BLS median annual salary
            bls_median_annual = None
            if bls_result and "median_pay" in bls_result:
                bls_median_annual = bls_result.get("median_pay")
                if isinstance(bls_median_annual, str):
                    # Extract numeric value from BLS result
                    bls_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', bls_median_annual)
                    if bls_match:
                        bls_median_annual = float(bls_match.group(1).replace(',', ''))
            
            # Extract salary.com data
            salary_com_data = None
            if salary_result and salary_result.get("success"):
                salary_com_data = salary_result.get("data", {})
                logger.info("📊 [JobStructurer] Salary.com data available: %s", salary_com_data.get("job_title", "N/A"))
            
            structured_jobs = []
            
            for job in scraped_jobs:
                # Extract salary information
                salary_data = self._extract_salary_range(job.get("salary", ""))
                
                # Convert to annual if needed
                min_annual = None
                max_annual = None
                if salary_data["min"] is not None:
                    min_annual = self._convert_salary_to_annual(salary_data["min"], salary_data["period"])
                if salary_data["max"] is not None:
                    max_annual = self._convert_salary_to_annual(salary_data["max"], salary_data["period"])
                
                # Determine experience level
                experience_level = self._determine_experience_level(job.get("experience", ""))
                
                # Create structured job entry
                structured_job = {
                    "job_title": job.get("job_title", job.get("title", "Unknown")),
                    "company": job.get("company", job.get("employer", "Unknown")),
                    "location": job.get("location", "Unknown"),
                    "experience_level": experience_level,
                    "experience_years": self.experience_levels[experience_level],
                    "min_salary_annual": min_annual,
                    "max_salary_annual": max_annual,
                    "min_salary_hourly": salary_data["min"] if salary_data["period"] == "hour" else None,
                    "max_salary_hourly": salary_data["max"] if salary_data["period"] == "hour" else None,
                    "currency": salary_data["currency"],
                    "bls_median_annual": bls_median_annual,
                    "salary_com_data": salary_com_data,  # Add salary.com data
                    "raw_salary_text": job.get("salary", ""),
                    "raw_experience_text": job.get("experience", ""),
                    "job_url": job.get("url", job.get("job_url", "")),
                    "posted_date": job.get("posted_date", job.get("date", ""))
                }
                
                structured_jobs.append(structured_job)
            
            # Sort by experience level (entry to expert)
            experience_order = ["level1", "level2", "level3", "level4", "level5"]
            structured_jobs.sort(key=lambda x: experience_order.index(x["experience_level"]))
            
            # Create summary statistics
            summary = self._create_summary_stats(structured_jobs, bls_median_annual, salary_com_data)
            
            return {
                "structured_jobs": structured_jobs,
                "summary": summary,
                "experience_levels": self.experience_levels,
                "total_jobs": len(structured_jobs),
                "structuring_status": "success",
                "salary_com_available": salary_com_data is not None
            }
            
        except Exception as e:
            logger.exception("❌ [JobStructurer] Error structuring job data: %s", e)
            return {
                "structured_jobs": [],
                "summary": {},
                "experience_levels": self.experience_levels,
                "total_jobs": 0,
                "structuring_status": "error",
                "structuring_error": str(e)
            }
    
    def _create_summary_stats(self, structured_jobs: List[Dict], bls_median: Optional[float], salary_com_data: Optional[Dict]) -> Dict[str, Any]:
        """Create summary statistics for the structured jobs"""
        if not structured_jobs:
            return {}
        
        # Filter jobs with valid salary data
        jobs_with_salary = [job for job in structured_jobs if job["min_salary_annual"] is not None]
        
        if not jobs_with_salary:
            return {"message": "No jobs with valid salary data"}
        
        # Calculate salary statistics
        min_salaries = [job["min_salary_annual"] for job in jobs_with_salary]
        max_salaries = [job["max_salary_annual"] for job in jobs_with_salary]
        
        summary = {
            "salary_range": {
                "min_annual": min(min_salaries),
                "max_annual": max(max_salaries),
                "avg_min_annual": sum(min_salaries) / len(min_salaries),
                "avg_max_annual": sum(max_salaries) / len(max_salaries)
            },
            "experience_distribution": {},
            "bls_comparison": {}
        }
        
        # Experience level distribution
        for level in self.experience_levels:
            level_jobs = [job for job in structured_jobs if job["experience_level"] == level]
            summary["experience_distribution"][level] = len(level_jobs)
        
        # BLS comparison if available
        if bls_median:
            summary["bls_comparison"] = {
                "bls_median_annual": bls_median,
                "jobs_above_bls": len([job for job in jobs_with_salary if job["max_salary_annual"] > bls_median]),
                "jobs_below_bls": len([job for job in jobs_with_salary if job["max_salary_annual"] < bls_median]),
                "bls_percentile": "N/A"  # Could be calculated if needed
            }
        
        # Salary.com comparison if available
        if salary_com_data:
            summary["salary_com_comparison"] = {
                "job_title": salary_com_data.get("job_title", "N/A"),
                "min_salary_annual": salary_com_data.get("min_salary_annual"),
                "max_salary_annual": salary_com_data.get("max_salary_annual"),
                "min_salary_hourly": salary_com_data.get("min_salary_hourly"),
                "max_salary_hourly": salary_com_data.get("max_salary_hourly"),
                "currency": salary_com_data.get("currency"),
                "period": salary_com_data.get("period")
            }
        
        return summary
    
    def export_to_table_format(self, structured_jobs: List[Dict]) -> List[List[str]]:
        """Export structured jobs to table format matching the PDF structure with salary.com data"""
        if not structured_jobs:
            return []
        
        # Table headers matching PDF format with salary.com data
        headers = [
            "Job Title",
            "Min Salary (Hourly)",
            "Max Salary (Hourly)", 
            "Min Salary (Annual)",
            "Max Salary (Annual)",
            "BLS Median (Annual)",
            "Salary.com Min (Annual)",
            "Salary.com Max (Annual)"
        ]
        
        table_data = [headers]
        
        # Add actual job data in the correct format
        for job in structured_jobs:
            # Format hourly rates (min and max)
            min_hourly = job["min_salary_hourly"] if job["min_salary_hourly"] else "N/A"
            max_hourly = job["max_salary_hourly"] if job["max_salary_hourly"] else "N/A"
            
            # Format annual rates
            min_annual = job["min_salary_annual"] if job["min_salary_annual"] else "N/A"
            max_annual = job["max_salary_annual"] if job["max_salary_annual"] else "N/A"
            
            # Format BLS median
            bls_median = job["bls_median_annual"] if job["bls_median_annual"] else "N/A"
            
            # Format salary.com data
            salary_com_data = job.get("salary_com_data", {})
            salary_com_min = salary_com_data.get("min_salary_annual") if salary_com_data else "N/A"
            salary_com_max = salary_com_data.get("max_salary_annual") if salary_com_data else "N/A"
            
            row = [
                job["job_title"],                                    # Job Title
                f"${min_hourly:.2f}" if isinstance(min_hourly, (int, float)) else min_hourly,  # Min (hourly)
                f"${max_hourly:.2f}" if isinstance(max_hourly, (int, float)) else max_hourly,  # Max (hourly)
                f"${min_annual:,.0f}" if isinstance(min_annual, (int, float)) else min_annual, # Min (annual)
                f"${max_annual:,.0f}" if isinstance(max_annual, (int, float)) else max_annual, # Max (annual)
                f"${bls_median:,.0f}" if isinstance(bls_median, (int, float)) else bls_median,  # BLS Median
                f"${salary_com_min:,.0f}" if isinstance(salary_com_min, (int, float)) else salary_com_min,  # Salary.com Min
                f"${salary_com_max:,.0f}" if isinstance(salary_com_max, (int, float)) else salary_com_max   # Salary.com Max
            ]
            table_data.append(row)
        
        return table_data

    def export_to_excel_format(self, structured_jobs: List[Dict], output_file: str = "structured_jobs.xlsx") -> str:
        """Export structured jobs to Excel format matching the WA - Seattle Sample.xlsx structure"""
        try:
            import pandas as pd
            
            # Create the table data
            table_data = self.export_to_table_format(structured_jobs)
            
            # Convert to DataFrame
            df = pd.DataFrame(table_data[1:], columns=table_data[0])
            
            # Write to Excel with specific formatting
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Job Data', index=False)
                
                # Get the workbook and worksheet
                workbook = writer.book
                worksheet = writer.sheets['Job Data']
                
                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            return f"Excel file exported successfully: {output_file}"
            
        except ImportError:
            return "pandas and openpyxl required for Excel export"
        except Exception as e:
            return f"Error exporting to Excel: {str(e)}"
