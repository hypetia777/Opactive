import streamlit as st
import requests
import pandas as pd
import os
import sys
from datetime import datetime

# Import centralized settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from config.settings import settings

st.set_page_config(page_title="💼 Job Market Query Interface", layout="wide")
st.title("💼 Automated Salary Insights System")

# Add some styling
st.markdown("""
<style>
.success-card {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
}
.warning-card {
    background-color: #fff3cd;
    border: 1px solid #ffeaa7;
    border-radius: 0.375rem;
    padding: 1rem;
    margin: 1rem 0;
}
.error-card {
    background-color: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 0.375rem;
    padding: 1rem 0;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)

# Input section
st.markdown("**Enter your job search query in the format: 'Job Title in Location'**")
st.markdown("*Examples: 'Software Engineer in New York', 'Data Scientist in San Francisco'*")

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Enter Job Title and Location", placeholder="e.g., Software Engineer in New York")
    with col2:
        st.write("")  # Spacing
        submit = st.form_submit_button("🔍 Search Jobs", type="primary")

if submit and query:
    with st.spinner("🔄 Processing your request..."):
        workflow_data = {}
        
        try:
            # Parse the query to extract job title and location
            # Expected format: "job title in location" or "job title, location"
            query_parts = query.split(" in ")
            if len(query_parts) == 2:
                job_title = query_parts[0].strip()
                location = query_parts[1].strip()
            else:
                # Try comma separation
                query_parts = query.split(",")
                if len(query_parts) == 2:
                    job_title = query_parts[0].strip()
                    location = query_parts[1].strip()
                else:
                    # Default: treat as job title, use default location
                    job_title = query.strip()
                    location = "United States"
            
            # Send properly formatted request
            request_data = {
                "job_title": job_title,
                "location": location,
                "max_results": 50
            }
            
            wf_response = requests.post(
                f"{os.getenv('BACKEND_URL', 'http://0.0.0.0:0000')}/jobs/query",
                json=request_data,
                timeout=300  # Increased timeout to 300 seconds (5 minutes)
            )
            wf_response.raise_for_status()
            workflow_data = wf_response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Network Error: Unable to connect to job service. {str(e)}")
        except Exception as e:
            st.error(f"❌ Failed to fetch from Full Workflow: {e}")

        if workflow_data:
            server_message = workflow_data.get('message', 'Query processed')
            server_status = workflow_data.get('status', 'unknown')

            all_validation_errors = []
            parsing_suggestions = []

            # Check for validation messages at different levels
            # 1. Direct top-level validation (from parsing server)
            if 'query_info' in workflow_data:
                query_info = workflow_data['query_info']
                validation_msg = query_info.get('message', '').strip()
                if validation_msg:
                    all_validation_errors.append(validation_msg)
                suggestions = query_info.get('suggestions', [])
                if suggestions:
                    parsing_suggestions.extend(suggestions)
            elif not workflow_data.get('is_valid', True):
                validation_msg = workflow_data.get('message', '').strip()
                if validation_msg:
                    all_validation_errors.append(validation_msg)
                suggestions = workflow_data.get('suggestions', [])
                if suggestions:
                    parsing_suggestions.extend(suggestions)

            # 2. Check validation in results
            if 'results' in workflow_data and 'validation' in workflow_data['results']:
                validation_info = workflow_data['results']['validation']
                if not validation_info.get('valid', True):
                    validation_msg = validation_info.get('message', '').strip()
                    if validation_msg and validation_msg not in all_validation_errors:
                        all_validation_errors.append(validation_msg)
                    suggestions = validation_info.get('suggestions', [])
                    if suggestions:
                        parsing_suggestions.extend(suggestions)


            # Show errors and suggestions
            message = workflow_data.get('message', '').strip()
            
            # If there's a missing field message from the parser
            if message and 'Missing required field' in message:
                st.error(f"❌ {message}")
            # If there are validation errors
            elif not workflow_data.get('is_valid', True) or server_status == 'validation_failed':
                message = workflow_data.get('message', '').strip()
                # Always show the backend's exact error message
                st.error(f"❌ {message}")

                # Do not show suggestions for any error

                # Show any additional validation errors
                for error in all_validation_errors:
                    if error and error != message:
                        st.error(f"❌ Additional validation error: {error}")

            elif server_status == 'success':
                pass  # Do not display the success message at all
            elif server_status in ['error', 'failed', 'validation_failed']:
                st.error(f"❌ {server_message}")
            elif server_status == 'warning' or 'warning' in server_message.lower():
                st.warning(f"⚠️ {server_message}")
            else:
                st.info(f"ℹ️ {server_message}")

            # Raw Debug View
            # with st.expander("🔧 Raw Server Response (for debugging)"):
            #     st.json(workflow_data)

            # Display BLS + Indeed Jobs in Expanders (instead of Tabs)
            with st.expander("📘 BLS Occupational Data"):
                # Get BLS data from the correct path in the response
                results = workflow_data.get("results", {})
                

                
                bls_result = results.get("bls_data", {})
                
                # Also check for BLS data from parallel execution
                if not bls_result:
                    bls_result = results.get("bls_result", {})

                # Check if bls_result has the actual BLS data
                actual_bls_data = bls_result.get("bls_result", {}) if isinstance(bls_result, dict) else bls_result
                
                if actual_bls_data and ("median_pay" in actual_bls_data or "job_title" in actual_bls_data):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("### 📋 Job Information")
                        st.markdown(f"**Job Title:** {actual_bls_data.get('job_title', 'N/A')}")
                        st.markdown(f"**Occupational Group:** {actual_bls_data.get('group_title', actual_bls_data.get('group', 'N/A'))}")
                        if actual_bls_data.get("url"):
                            st.markdown(f"[📄 View Full BLS Report]({actual_bls_data.get('url')})")
                    with col2:
                        st.markdown("### 💰 Compensation")
                        median_pay = actual_bls_data.get('median_pay', 'N/A')
                        st.markdown(f"**Median Annual Salary:** {median_pay}")
                        if 'per hour' in str(median_pay).lower():
                            st.markdown("*Includes hourly rate information*")

                    # Removed Additional Details section for BLS
                else:
                    st.warning("🔍 No BLS occupational data found for this query.")
                    if isinstance(bls_result, dict):
                        alternatives = bls_result.get("alternatives", [])
                        if alternatives:
                            st.markdown("### 🔄 Suggested Alternatives:")
                            for alt in alternatives:
                                st.markdown(f"• {alt}")
                    st.info("💡 **Tip:** Try using more general job titles or check official occupation classifications.")

            # NEW: Salary.com Data Expander
            with st.expander("💰 Salary.com Compensation Data"):
                results = workflow_data.get("results", {})
                

                
                salary_result = results.get("salary_data", {})
                
                # Also check for salary data from parallel execution
                if not salary_result:
                    salary_result = results.get("salary_result", {})

                # Check if salary_result has the actual salary data
                actual_salary_data = salary_result.get("salary_result", {}) if isinstance(salary_result, dict) else salary_result
                
                if actual_salary_data and actual_salary_data.get("success"):
                    data = actual_salary_data.get("data", {})
                    scraping_time = actual_salary_data.get("scraping_time", 0)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("### 📋 Job Information")
                        st.markdown(f"**Job Title:** {data.get('job_title', 'N/A')}")
                        st.markdown(f"**City:** {data.get('city', 'N/A')}")
                        st.markdown(f"**Education Level:** {data.get('education_level', 'N/A')}")
                        st.markdown(f"**Experience:** {data.get('experience_years', 'N/A')} years")
                        st.markdown(f"**Scraping Time:** {scraping_time}s")
                    
                    with col2:
                        st.markdown("### 💰 Compensation Data")
                        total_rows = data.get("total_rows", 0)
                        st.markdown(f"**Total Data Points:** {total_rows}")
                        
                        if total_rows > 0:
                            st.success(f"✅ Successfully extracted {total_rows} compensation records")
                        else:
                            st.warning("⚠️ No compensation data extracted")
                    
                    # Show table data if available
                    table_headers = data.get("table_headers", [])
                    table_rows = data.get("table_rows", [])
                    
                    if table_headers and table_rows:
                        st.markdown("### 📊 Compensation Data Table")
                        st.markdown(f"**Columns:** {len(table_headers)} | **Rows:** {len(table_rows)}")
                        
                        # Fix column count mismatch and duplicate column names
                        if len(table_headers) != len(table_rows[0]) if table_rows else 0:
                            st.warning(f"⚠️ Column count mismatch: {len(table_headers)} headers vs {len(table_rows[0]) if table_rows else 0} data columns")
                            # Use the smaller count to avoid errors
                            column_count = min(len(table_headers), len(table_rows[0]) if table_rows else 0)
                            table_headers = table_headers[:column_count]
                        
                        # Fix duplicate column names by making them unique
                        unique_headers = []
                        seen_headers = set()
                        for i, header in enumerate(table_headers):
                            if header == '' or header in seen_headers:
                                # Create unique name for empty or duplicate headers
                                unique_headers.append(f"Column_{i+1}")
                            else:
                                unique_headers.append(header)
                                seen_headers.add(header)
                        
                        # Create a DataFrame for better display
                        df_salary = pd.DataFrame(table_rows, columns=unique_headers)
                        st.dataframe(df_salary, use_container_width=True)
                        
                        # Download button for salary data
                        csv_salary = df_salary.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Salary Data as CSV",
                            data=csv_salary,
                            file_name=f"salary_data_{data.get('job_title', 'job').replace(' ', '_')}_{data.get('city', 'location').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("📝 Table data not available. Check server logs for detailed extraction.")
                        
                elif salary_result and "error" in salary_result:
                    st.error(f"❌ Salary.com scraping failed: {salary_result.get('error', 'Unknown error')}")
                    if salary_result.get("scraping_time"):
                        st.info(f"⏱️ Time spent: {salary_result.get('scraping_time')}s")
                else:
                    st.warning("🔍 No Salary.com compensation data found for this query.")
                    st.info("💡 **Tip:** The Salary.com server may not be running or the scraping may have failed.")

            with st.expander("🌐 Indeed Job Listings"):
                # Get jobs from the correct path in the response
                results = workflow_data.get("results", {})
                jobs = results.get("jobs", [])
                
                # Also check for scraped jobs from parallel execution
                if not jobs:
                    jobs = results.get("scraped_jobs", [])
                
                # Only create DataFrame if we have jobs
                if jobs:
                    df = pd.DataFrame(jobs)
                else:
                    df = pd.DataFrame()
                
                # Check for success status at both levels
                if workflow_data.get("status") == "success" or workflow_data.get("results", {}).get("total_found", 0) > 0:
                    if jobs:
                        st.success(f"✅ Found {len(jobs)} job listing(s)")
                        # Removed metrics display (Total Jobs, Unique Companies, Unique Locations)
                        if 'url' in df.columns:
                            def make_clickable(url):
                                return f'<a href="{url}" target="_blank">View Job</a>' if pd.notna(url) else ''
                            df['Link'] = df['url'].apply(make_clickable)

                        st.dataframe(df, use_container_width=True)
                    else:
                        st.warning("🔍 No job listings found.")
                        st.markdown("""
                        ### 💡 Try These Tips:
                        - Use broader search terms
                        - Try alternative job titles
                        - Check different locations
                        """)
                    # Always show the download button
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Results as CSV",
                        data=csv,
                        file_name=f"job_results_{query.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        disabled=len(jobs) == 0
                    )
                else:
                    st.error(f"❌ Job Search Error: {workflow_data.get('message', 'Unknown error')}")



        else:
            st.error("❌ Unable to process request. Please check your connection and try again.")

# Sidebar
with st.sidebar:
    st.markdown("## 📚 Help & Tips")
    st.markdown("""
    ### 🎯 Search Tips:
    - Format: 'Job Title in Location'
    - Example: 'Software Engineer in San Francisco'
    
    ### 📊 Data Sources:
    - **BLS**: Official occupation data & median salaries
    - **Salary.com**: Detailed compensation data & market analysis
    - **Indeed**: Job listings & current openings

    ### 🚀 Parallel Processing:
    - All three data sources run simultaneously
    - Faster results with comprehensive data coverage

    ### 🛠 Troubleshooting:
    - If no data appears, try rephrasing your query
    - Ensure job titles and locations are valid
    - Are you connected to the internet?
    """)
