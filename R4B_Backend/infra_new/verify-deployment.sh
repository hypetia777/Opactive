#!/bin/bash

# =============================================================================
# OpActive R4B Deployment Verification Script
# =============================================================================
# PHASE 6: TESTING & VERIFICATION
# This script comprehensively tests the deployed infrastructure
# 
# Usage: ./verify-deployment.sh [stage]
# stage: demo|dev|staging|prod (default: demo)
#
# Tests performed:
# 1. Infrastructure validation
# 2. Service health checks
# 3. Load balancer routing
# 4. Service discovery
# 5. Container connectivity
# 6. Application functionality
# =============================================================================

set -e

# Default values
STAGE=${1:-demo}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

test_start() {
    ((TESTS_TOTAL++))
    echo -e "${BLUE}[TEST $TESTS_TOTAL]${NC} $1"
}

test_pass() {
    ((TESTS_PASSED++))
    echo -e "${GREEN}  ✓ PASSED${NC} $1"
}

test_fail() {
    ((TESTS_FAILED++))
    echo -e "${RED}  ✗ FAILED${NC} $1"
}

# Get stack information
get_stack_outputs() {
    local app_stack_name="R4B-OpActive-App-${STAGE^}"
    local vpc_stack_name="R4B-OpActive-VPC-${STAGE^}"
    local region="us-west-1"
    
    log_info "Getting stack outputs for verification..."
    
    # Get Application outputs
    APP_URL=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ApplicationURL'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='APIURL'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    CLUSTER_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ECSClusterName'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [[ -z "$APP_URL" || -z "$API_URL" || -z "$CLUSTER_NAME" ]]; then
        log_error "Failed to retrieve stack outputs. Make sure the application is deployed."
        exit 1
    fi
    
    log_success "Stack outputs retrieved successfully"
    log_info "Application URL: $APP_URL"
    log_info "API URL: $API_URL"
    log_info "ECS Cluster: $CLUSTER_NAME"
}

# Test 1: CloudFormation Stack Health
test_cloudformation_stacks() {
    test_start "CloudFormation Stack Health"
    
    local app_stack_name="R4B-OpActive-App-${STAGE^}"
    local vpc_stack_name="R4B-OpActive-VPC-${STAGE^}"
    local region="us-west-1"
    
    # Check VPC stack
    local vpc_status=$(aws cloudformation describe-stacks \
        --stack-name "$vpc_stack_name" \
        --region "$region" \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$vpc_status" == "CREATE_COMPLETE" || "$vpc_status" == "UPDATE_COMPLETE" ]]; then
        test_pass "VPC stack is healthy: $vpc_status"
    else
        test_fail "VPC stack is unhealthy: $vpc_status"
        return 1
    fi
    
    # Check Application stack
    local app_status=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$app_status" == "CREATE_COMPLETE" || "$app_status" == "UPDATE_COMPLETE" ]]; then
        test_pass "Application stack is healthy: $app_status"
    else
        test_fail "Application stack is unhealthy: $app_status"
        return 1
    fi
}

# Test 2: ECS Service Health
test_ecs_services() {
    test_start "ECS Service Health"
    
    local services=("bls-service" "salary-service" "fastapi-service" "streamlit-service" "scraping-service")
    local region="us-west-1"
    local all_healthy=true
    
    for service in "${services[@]}"; do
        local service_status=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$service" \
            --region "$region" \
            --query "services[0].status" \
            --output text 2>/dev/null || echo "MISSING")
        
        local running_count=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$service" \
            --region "$region" \
            --query "services[0].runningCount" \
            --output text 2>/dev/null || echo "0")
        
        local desired_count=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$service" \
            --region "$region" \
            --query "services[0].desiredCount" \
            --output text 2>/dev/null || echo "0")
        
        if [[ "$service_status" == "ACTIVE" && "$running_count" == "$desired_count" && "$running_count" -gt 0 ]]; then
            test_pass "$service: $service_status ($running_count/$desired_count tasks running)"
        else
            test_fail "$service: $service_status ($running_count/$desired_count tasks running)"
            all_healthy=false
        fi
    done
    
    if [[ "$all_healthy" == "true" ]]; then
        test_pass "All ECS services are healthy"
    else
        test_fail "Some ECS services are unhealthy"
        return 1
    fi
}

# Test 3: Load Balancer Target Health
test_load_balancer_targets() {
    test_start "Load Balancer Target Health"
    
    local region="us-west-1"
    local app_stack_name="R4B-OpActive-App-${STAGE^}"
    
    # Get target group ARNs
    local fastapi_tg_arn=$(aws cloudformation describe-stack-resources \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "StackResources[?LogicalResourceId=='FastAPITargetGroup'].PhysicalResourceId" \
        --output text 2>/dev/null || echo "")
    
    local streamlit_tg_arn=$(aws cloudformation describe-stack-resources \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "StackResources[?LogicalResourceId=='StreamlitTargetGroup'].PhysicalResourceId" \
        --output text 2>/dev/null || echo "")
    
    # Check FastAPI target group
    if [[ -n "$fastapi_tg_arn" ]]; then
        local fastapi_healthy=$(aws elbv2 describe-target-health \
            --target-group-arn "$fastapi_tg_arn" \
            --region "$region" \
            --query "TargetHealthDescriptions[?TargetHealth.State=='healthy']" \
            --output text 2>/dev/null | wc -l)
        
        if [[ "$fastapi_healthy" -gt 0 ]]; then
            test_pass "FastAPI target group has $fastapi_healthy healthy targets"
        else
            test_fail "FastAPI target group has no healthy targets"
        fi
    else
        test_fail "FastAPI target group not found"
    fi
    
    # Check Streamlit target group
    if [[ -n "$streamlit_tg_arn" ]]; then
        local streamlit_healthy=$(aws elbv2 describe-target-health \
            --target-group-arn "$streamlit_tg_arn" \
            --region "$region" \
            --query "TargetHealthDescriptions[?TargetHealth.State=='healthy']" \
            --output text 2>/dev/null | wc -l)
        
        if [[ "$streamlit_healthy" -gt 0 ]]; then
            test_pass "Streamlit target group has $streamlit_healthy healthy targets"
        else
            test_fail "Streamlit target group has no healthy targets"
        fi
    else
        test_fail "Streamlit target group not found"
    fi
}

# Test 4: Application Endpoint Connectivity
test_application_endpoints() {
    test_start "Application Endpoint Connectivity"
    
    # Test main application (Streamlit)
    if curl -f -s --max-time 30 "$APP_URL" > /dev/null; then
        test_pass "Main application is accessible: $APP_URL"
    else
        test_fail "Main application is not accessible: $APP_URL"
    fi
    
    # Test API documentation
    if curl -f -s --max-time 30 "$API_URL" > /dev/null; then
        test_pass "API documentation is accessible: $API_URL"
    else
        test_fail "API documentation is not accessible: $API_URL"
    fi
    
    # Test API health endpoint
    local health_url="${APP_URL}/api/jobs/health"
    if curl -f -s --max-time 30 "$health_url" > /dev/null; then
        test_pass "API health endpoint is accessible: $health_url"
    else
        test_fail "API health endpoint is not accessible: $health_url"
    fi
}

# Test 5: Service Discovery
test_service_discovery() {
    test_start "Service Discovery"
    
    local region="us-west-1"
    local namespace_name="R4B-OpActive-${STAGE}.local"
    
    # Check if namespace exists
    local namespace_id=$(aws servicediscovery list-namespaces \
        --region "$region" \
        --query "Namespaces[?Name=='$namespace_name'].Id" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$namespace_id" ]]; then
        test_pass "Service discovery namespace exists: $namespace_name"
        
        # Check services in namespace
        local services=$(aws servicediscovery list-services \
            --region "$region" \
            --query "Services[?NamespaceId=='$namespace_id'].Name" \
            --output text 2>/dev/null || echo "")
        
        local expected_services=("bls-server" "salary-server" "fastapi-server" "streamlit-server" "scraping-server")
        local found_count=0
        
        for service in "${expected_services[@]}"; do
            if echo "$services" | grep -q "$service"; then
                ((found_count++))
            fi
        done
        
        if [[ "$found_count" -eq 5 ]]; then
            test_pass "All 5 services registered in service discovery"
        else
            test_fail "Only $found_count/5 services registered in service discovery"
        fi
    else
        test_fail "Service discovery namespace not found: $namespace_name"
    fi
}

# Test 6: Container Logs Accessibility
test_container_logs() {
    test_start "Container Logs Accessibility"
    
    local region="us-west-1"
    local log_groups=("/ecs/R4B-OpActive-${STAGE}-bls-service" 
                     "/ecs/R4B-OpActive-${STAGE}-salary-service" 
                     "/ecs/R4B-OpActive-${STAGE}-fastapi-service" 
                     "/ecs/R4B-OpActive-${STAGE}-streamlit-service" 
                     "/ecs/R4B-OpActive-${STAGE}-scraping-service")
    
    local logs_accessible=true
    
    for log_group in "${log_groups[@]}"; do
        if aws logs describe-log-groups \
            --log-group-name-prefix "$log_group" \
            --region "$region" \
            --query "logGroups[?logGroupName=='$log_group']" \
            --output text > /dev/null 2>&1; then
            test_pass "Log group accessible: $log_group"
        else
            test_fail "Log group not accessible: $log_group"
            logs_accessible=false
        fi
    done
    
    if [[ "$logs_accessible" == "true" ]]; then
        test_pass "All container log groups are accessible"
    else
        test_fail "Some container log groups are not accessible"
    fi
}

# Test 7: Security Group Configuration
test_security_groups() {
    test_start "Security Group Configuration"
    
    local region="us-west-1"
    local vpc_stack_name="R4B-OpActive-VPC-${STAGE^}"
    
    # Get security group IDs
    local alb_sg_id=$(aws cloudformation describe-stacks \
        --stack-name "$vpc_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ALBSecurityGroupId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$alb_sg_id" ]]; then
        # Check ALB security group rules
        local alb_rules=$(aws ec2 describe-security-groups \
            --group-ids "$alb_sg_id" \
            --region "$region" \
            --query "SecurityGroups[0].IpPermissions[?FromPort==\`80\`]" \
            --output text 2>/dev/null || echo "")
        
        if [[ -n "$alb_rules" ]]; then
            test_pass "ALB security group has correct HTTP rules"
        else
            test_fail "ALB security group missing HTTP rules"
        fi
    else
        test_fail "ALB security group not found"
    fi
}

# Test 8: Auto Scaling Configuration
test_auto_scaling() {
    test_start "Auto Scaling Configuration"
    
    local region="us-west-1"
    local scalable_targets=$(aws application-autoscaling describe-scalable-targets \
        --service-namespace ecs \
        --region "$region" \
        --query "ScalableTargets[?contains(ResourceId,'$CLUSTER_NAME')]" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$scalable_targets" ]]; then
        test_pass "Auto scaling targets are configured"
    else
        test_warning "No auto scaling targets found (may be expected for demo)"
    fi
}

# Test 9: CloudWatch Monitoring
test_cloudwatch_monitoring() {
    test_start "CloudWatch Monitoring"
    
    local region="us-west-1"
    local dashboard_name="R4B-OpActive-${STAGE}-Dashboard"
    
    # Check if dashboard exists
    if aws cloudwatch get-dashboard \
        --dashboard-name "$dashboard_name" \
        --region "$region" > /dev/null 2>&1; then
        test_pass "CloudWatch dashboard exists: $dashboard_name"
    else
        test_fail "CloudWatch dashboard not found: $dashboard_name"
    fi
    
    # Check for CloudWatch alarms
    local alarms=$(aws cloudwatch describe-alarms \
        --alarm-name-prefix "R4B-OpActive-${STAGE}" \
        --region "$region" \
        --query "MetricAlarms[].AlarmName" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$alarms" ]]; then
        test_pass "CloudWatch alarms are configured"
    else
        test_warning "No CloudWatch alarms found"
    fi
}

# Test 10: End-to-End Application Test
test_application_functionality() {
    test_start "End-to-End Application Functionality"
    
    # Test API endpoint with a simple query
    local api_test_url="${APP_URL}/api/jobs/health"
    local response=$(curl -s --max-time 30 "$api_test_url" 2>/dev/null || echo "")
    
    if echo "$response" | grep -q "healthy\|status"; then
        test_pass "API responds with health status"
    else
        test_fail "API does not respond properly"
    fi
    
    # Test if Streamlit app loads basic content
    local streamlit_content=$(curl -s --max-time 30 "$APP_URL" 2>/dev/null || echo "")
    
    if echo "$streamlit_content" | grep -q -i "streamlit\|opactive\|salary"; then
        test_pass "Streamlit application loads with expected content"
    else
        test_fail "Streamlit application does not load properly"
    fi
}

# Generate verification report
generate_report() {
    echo
    echo "=========================================="
    echo "     DEPLOYMENT VERIFICATION REPORT"
    echo "=========================================="
    echo "Environment: $STAGE"
    echo "Date: $(date)"
    echo "Tests Total: $TESTS_TOTAL"
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}🎉 ALL TESTS PASSED! Deployment is healthy.${NC}"
        echo
        log_success "Verification completed successfully"
        echo "Your OpActive R4B application is ready to use:"
        echo "• Application: $APP_URL"
        echo "• API Docs: $API_URL"
        echo
    else
        echo -e "${RED}❌ SOME TESTS FAILED! Please review the issues above.${NC}"
        echo
        log_error "Verification found issues that need attention"
        echo
        echo "Common troubleshooting steps:"
        echo "1. Check ECS service logs: aws logs tail /ecs/R4B-OpActive-${STAGE}-[service-name] --follow"
        echo "2. Check service status: aws ecs describe-services --cluster $CLUSTER_NAME --services [service-name]"
        echo "3. Check load balancer targets: aws elbv2 describe-target-health --target-group-arn [tg-arn]"
        echo
        return 1
    fi
}

# Main execution
main() {
    echo "=== OpActive R4B Deployment Verification ==="
    echo "Stage: $STAGE"
    echo "Starting comprehensive verification tests..."
    echo
    
    # Validate inputs
    if [[ ! "$STAGE" =~ ^(demo|dev|staging|prod)$ ]]; then
        log_error "Invalid stage: $STAGE. Must be one of: demo, dev, staging, prod"
        exit 1
    fi
    
    # Check prerequisites
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is required but not installed"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi
    
    # Get stack information
    get_stack_outputs
    
    # Run all tests
    test_cloudformation_stacks
    test_ecs_services
    test_load_balancer_targets
    test_application_endpoints
    test_service_discovery
    test_container_logs
    test_security_groups
    test_auto_scaling
    test_cloudwatch_monitoring
    test_application_functionality
    
    # Generate report
    generate_report
}

# Helper function for warnings
test_warning() {
    echo -e "${YELLOW}  ⚠ WARNING${NC} $1"
}

# Run main function
main "$@"
