import streamlit as st
import requests
import pandas as pd
import os
import sys
from datetime import datetime
# Import centralized settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
# --- Add these session state variables at the top ---
if 'conversation' not in st.session_state:
    st.session_state.conversation = []  # List of (role, message) tuples
if 'pending_query' not in st.session_state:
    st.session_state.pending_query = ""
if 'follow_up_question' not in st.session_state:
    st.session_state.follow_up_question = None
if 'missing_fields' not in st.session_state:
    st.session_state.missing_fields = []
if 'current_query' not in st.session_state:
    st.session_state.current_query = ""
# Input section
st.markdown("**Enter your job search query with education and experience**")
st.markdown("*Examples: 'Data Engineer in Mexico with Bachelor's degree and 5 years experience', 'Software Developer in New York with Master's degree and 3 years experience'*")
# --- Simplified Chat UI ---
# Display conversation history
for role, msg in st.session_state.conversation:
    if role == "user":
        st.markdown(f"**You:** {msg}")
    else:
        st.markdown(f"**Bot:** {msg}")
# Input box for user message
if st.session_state.follow_up_question:
    user_input = st.text_input("Bot asks:", value="", placeholder=st.session_state.follow_up_question, key="followup_input")
else:
    user_input = st.text_input("Type your job query:", value="", placeholder="e.g., HVAC Technician in Seattle with Bachelor's degree and 5 years experience", key="main_input")
submit = st.button("Send")
if submit and user_input:
    # Add user message to conversation
    st.session_state.conversation.append(("user", user_input))
    if st.session_state.follow_up_question:
        # Combine previous query and follow-up answer
        combined_query = f"{st.session_state.current_query} {user_input}"
        st.session_state.current_query = combined_query
        query_to_send = combined_query
        st.session_state.follow_up_question = None
    else:
        query_to_send = user_input
        st.session_state.current_query = user_input
    with st.spinner("🤖 Bot is thinking..."):
        try:
            request_data = {
                "query": query_to_send,
                "max_results": 5
            }
            wf_response = requests.post(
                "http://13.57.212.168:8000/jobs/query",
                json=request_data,
                timeout=300
            )
            wf_response.raise_for_status()
            workflow_data = wf_response.json()
            
            # Store the workflow data in session state
            st.session_state.workflow_data = workflow_data
            
            # Store workflow data for processing
            # If follow-up is needed, ask next question
            if workflow_data.get("needs_follow_up", False):
                follow_up = workflow_data.get("follow_up_question", "Please provide more information.")
                missing_fields = workflow_data.get("missing_fields", [])
                all_follow_up_questions = workflow_data.get("all_follow_up_questions", [])
                
                # Create a more informative message showing what's missing
                if missing_fields:
                    missing_display = ", ".join(missing_fields).replace("_", " ").title()
                    follow_up_with_context = f"I need more information. Missing: {missing_display}. {follow_up}"
                else:
                    follow_up_with_context = follow_up
                
                st.session_state.follow_up_question = follow_up
                st.session_state.missing_fields = missing_fields
                st.session_state.conversation.append(("bot", follow_up_with_context))
                st.rerun()
            else:
                # Show final results as bot message
                result_msg = workflow_data.get("message", "Query processed.")
                st.session_state.conversation.append(("bot", result_msg))
                # Store the workflow data for display
                st.session_state.workflow_data = workflow_data
                st.rerun()
        except requests.exceptions.RequestException as e:
            st.session_state.conversation.append(("bot", f"❌ Network Error: {str(e)}"))
        except Exception as e:
            st.session_state.conversation.append(("bot", f"❌ Failed to process: {e}"))
# Optionally, add a "Reset Conversation" button
if st.button("Reset Conversation"):
    st.session_state.conversation = []
    st.session_state.follow_up_question = None
    st.session_state.current_query = ""
    st.session_state.workflow_data = None
# Get workflow data from session state
workflow_data = st.session_state.get('workflow_data', None)
# Structured Excel-Format Salary Data Section - Only show after workflow completion
if workflow_data:
    results = workflow_data.get("results", {})
    excel_data = results.get("excel_data", [])
    table_data = results.get("table_data", [])
    structuring_status = results.get("structuring_status", "unknown")
    structuring_completed = results.get("structuring_completed", False)
    workflow_status = workflow_data.get("status", "unknown")
    
    # Only show structured data section when workflow is completed successfully
    if (workflow_status == "success" and 
        structuring_completed and 
        structuring_status == "success" and 
        table_data):
        
        
        st.markdown("---")
        st.markdown("## 📊 Structured Salary Data (Excel Format)")
        # Define column headers matching the exact format from the image
        excel_columns = [
            "Job Title",
            "Market Average",  # Annual sub-column
            "Market Average",  # Hourly sub-column  
            "Min",  # Annual sub-column
            "Min",  # Hourly sub-column
            "Max",  # Annual sub-column
            "Max",  # Hourly sub-column
            "Notes",
            "BLS National Average",
            "Cost of living compared to National Average",
            "Last updated"
        ]
        
        # Create DataFrame with the structured data using grouped columns
        if table_data and len(table_data) > 0:
            
            # Check if this is the new salary table format (dictionary-based)
            if isinstance(table_data[0], dict):
                # New format: list of dictionaries with keys like 'job_title', 'market_average_annual', etc.
                formatted_rows = []
                
                # Separate main job row from level rows
                main_job_row = None
                level_rows = []
                
                for row in table_data:
                    if row.get('is_sub_row'):
                        level_rows.append(row)
                    else:
                        main_job_row = row
                
                # Add main job row first
                if main_job_row:
                    formatted_rows.append([
                        main_job_row.get('job_title', ''),  # Job Title
                        '',  # Market Average Annual
                        '',  # Market Average Hourly
                        '',  # Min Annual
                        '',  # Min Hourly
                        '',  # Max Annual
                        '',  # Max Hourly
                        '',  # Notes
                        main_job_row.get('bls_national_average', ''),  # BLS National Average
                        main_job_row.get('cost_of_living', ''),  # Cost of Living
                        main_job_row.get('last_updated', '')  # Last Updated
                    ])
                
                # Add level rows
                for row in level_rows:
                    formatted_row = [
                        row.get('job_title', ''),  # Job Title (Level 1, Level 2, etc.)
                        row.get('market_average_annual', ''),  # Market Average Annual
                        row.get('market_average_hourly', ''),  # Market Average Hourly
                        row.get('min_annual', ''),  # Min Annual
                        row.get('min_hourly', ''),  # Min Hourly
                        row.get('max_annual', ''),  # Max Annual
                        row.get('max_hourly', ''),  # Max Hourly
                        row.get('notes', ''),  # Notes
                        '',  # BLS National Average (empty for levels)
                        '',  # Cost of Living (empty for levels)
                        row.get('last_updated', '')  # Last Updated
                    ]
                    formatted_rows.append(formatted_row)
            else:
                # Old format: list of lists
                formatted_rows = []
                for row in table_data:
                    if len(row) >= 7:  # Ensure we have enough data
                        # Reorganize data for grouped columns with better spacing
                        # Original: [Job Title, Market Avg Annual, Market Avg Hourly, Min Annual, Min Hourly, Max Annual, Max Hourly, Notes, BLS, Cost of Living, Last Updated]
                        # New: [Job Title, Market Avg (Annual|Hourly), Min (Annual|Hourly), Max (Annual|Hourly), Notes, BLS, Cost of Living, Last Updated]
                        
                        # Use separate columns for annual and hourly values to match the new format
                        grouped_row = [
                            row[0],  # Job Title
                            row[1] if len(row) > 1 else "",  # Market Average Annual
                            row[2] if len(row) > 2 else "",  # Market Average Hourly
                            row[3] if len(row) > 3 else "",  # Min Annual
                            row[4] if len(row) > 4 else "",  # Min Hourly
                            row[5] if len(row) > 5 else "",  # Max Annual
                            row[6] if len(row) > 6 else "",  # Max Hourly
                            row[7] if len(row) > 7 else "",  # Notes
                            row[8] if len(row) > 8 else "",  # BLS National Average
                            row[9] if len(row) > 9 else "",  # Cost of Living
                            row[10] if len(row) > 10 else ""  # Last Updated
                        ]
                        formatted_rows.append(grouped_row)
                    else:
                        # Fallback for incomplete rows
                        grouped_row = [row[0] if len(row) > 0 else ""] + [""] * (len(excel_columns) - 1)
                        formatted_rows.append(grouped_row)
            
            df_excel = pd.DataFrame(formatted_rows, columns=excel_columns)
            
            # Create MultiIndex columns to match the image format
            columns_tuples = [
                ('Job Title', ''),
                ('Market Average', 'Annual'),
                ('Market Average', 'Hourly'),
                ('Min', 'Annual'),
                ('Min', 'Hourly'),
                ('Max', 'Annual'),
                ('Max', 'Hourly'),
                ('Notes', ''),
                ('BLS National Average', ''),
                ('Cost of living compared to National Average', ''),
                ('Last updated', '')
            ]
            
            df_excel.columns = pd.MultiIndex.from_tuples(columns_tuples)
            
            # Display the Excel-format table with custom styling
            st.markdown("### 💼 Salary Analysis Table")
            
            # Add custom CSS for better table formatting
            st.markdown("""
            <style>
            .salary-table {
                font-family: 'Arial', sans-serif;
                border-collapse: collapse;
                width: 100%;
            }
            .salary-table th {
                background-color: #4A90E2;
                color: white;
                font-weight: bold;
                text-align: center;
                padding: 8px;
                border: 1px solid #ddd;
            }
            .salary-table td {
                font-size: 0.9em;
                padding: 8px;
                border: 1px solid #ddd;
                text-align: right;
            }
            .salary-table td:first-child {
                text-align: left;
            }
            .salary-table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .salary-table tr:hover {
                background-color: #f5f5f5;
            }
            </style>
            """, unsafe_allow_html=True)
            
            st.dataframe(df_excel, use_container_width=True)
            
            # Download button for Excel format data
            csv_excel = df_excel.to_csv(index=False)
            st.download_button(
                label="📥 Download Excel Format Data as CSV",
                data=csv_excel,
                file_name=f"salary_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            # Show key metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                # Extract hourly rates from the Market Average Hourly column
                try:
                    hourly_column = ('Market Average', 'Hourly')
                    if hourly_column in df_excel.columns:
                        hourly_values = df_excel[hourly_column].apply(lambda x: float(str(x).replace('$', '').replace(',', '')) if str(x).replace('$', '').replace(',', '').replace('.', '').isdigit() else 0)
                        avg_market = hourly_values.mean()
                        if avg_market > 0:
                            st.metric("Avg Market Rate/Hour", f"${avg_market:.2f}")
                        else:
                            st.metric("Avg Market Rate/Hour", "N/A")
                    else:
                        st.metric("Avg Market Rate/Hour", "N/A")
                except Exception as e:
                    st.metric("Avg Market Rate/Hour", "N/A")
            
            with col2:
                unique_titles = df_excel[('Job Title', '')].nunique()
                st.metric("Experience Levels", unique_titles)
            
            with col3:
                bls_column = ('BLS National Average', '')
                if bls_column in df_excel.columns:
                    has_bls_data = (df_excel[bls_column] != "").sum()
                    st.metric("Records with BLS Data", has_bls_data)
                else:
                    st.metric("Records with BLS Data", 0)
            
        else:
            st.warning("⚠️ No table data available to display")
            
    elif workflow_status == "success" and structuring_status == "error":
        st.markdown("---")
        st.markdown("## 📊 Structured Salary Data (Excel Format)")
        error_msg = results.get("structuring_error", "Unknown error")
        st.error(f"❌ Error processing salary data: {error_msg}")
        
    elif workflow_status == "success" and not structuring_completed:
        # Workflow completed but structuring may still be in progress
        st.info("⏳ Processing salary data...")
        
    elif workflow_status in ["error", "failed"]:
        # Don't show structured data section for failed workflows
        pass
        
    # For any other case where workflow is successful but no structured data
    elif workflow_status == "success":
        st.markdown("---") 
        st.markdown("## 📊 Structured Salary Data (Excel Format)")
        st.info("📊 No structured salary data available. The workflow completed but no salary data was processed.")

# No workflow data available yet
else:
    pass  # Don't show anything until there's workflow data

# Workflow data processing logic

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