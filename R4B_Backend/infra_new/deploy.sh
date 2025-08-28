#!/bin/bash

# =============================================================================
# OpActive R4B Complete Infrastructure Deployment Script
# =============================================================================
# This script deploys both AccountLevel (VPC) and Application infrastructure
# 
# Usage: ./deploy.sh [stage] [action]
# stage: demo|dev|staging|prod (default: demo)
# action: deploy|delete|validate (default: deploy)
#
# Examples:
#   ./deploy.sh demo deploy     # Deploy demo environment
#   ./deploy.sh prod validate   # Validate prod templates
#   ./deploy.sh dev delete      # Delete dev environment
# =============================================================================

set -e  # Exit on any error

# Default values
STAGE=${1:-demo}
ACTION=${2:-deploy}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Validate inputs
validate_inputs() {
    if [[ ! "$STAGE" =~ ^(demo|dev|staging|prod)$ ]]; then
        log_error "Invalid stage: $STAGE. Must be one of: demo, dev, staging, prod"
        exit 1
    fi
    
    if [[ ! "$ACTION" =~ ^(deploy|delete|validate)$ ]]; then
        log_error "Invalid action: $ACTION. Must be one of: deploy, delete, validate"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is required but not installed"
        exit 1
    fi
    
    # Check SAM CLI
    if ! command -v sam &> /dev/null; then
        log_error "SAM CLI is required but not installed"
        log_info "Install from: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
        exit 1
    fi
    
    # Check Docker (for building images)
    if ! command -v docker &> /dev/null; then
        log_warning "Docker is not installed. You'll need it to build container images."
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Validate CloudFormation templates
validate_templates() {
    log_info "Validating CloudFormation templates..."
    
    # Validate AccountLevel template
    log_info "Validating AccountLevel template..."
    sam validate --template AccountLevel/template.yaml --region us-west-1
    
    # Validate Application template
    log_info "Validating Application template..."
    sam validate --template template.yaml --region us-west-1
    
    log_success "Template validation passed"
}

# Deploy AccountLevel infrastructure (VPC, Security Groups)
deploy_account_level() {
    log_info "Checking if AccountLevel infrastructure needs to be deployed..."
    
    local stack_name="R4B-VPC-Main"
    local region="us-west-1"
    
    # Check if the stack already exists
    if aws cloudformation describe-stacks --stack-name "$stack_name" --region "$region" > /dev/null 2>&1; then
        log_success "AccountLevel infrastructure (VPC) already exists: $stack_name"
        log_info "Checking if it needs security group updates for containers..."
        
        # Check if ALB security group exists
        local alb_sg_exists=$(aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --region "$region" \
            --query "Stacks[0].Outputs[?OutputKey=='ALBSecurityGroupId'].OutputValue" \
            --output text 2>/dev/null || echo "")
        
        if [[ -z "$alb_sg_exists" ]]; then
            log_warning "Container security groups not found. Updating AccountLevel stack..."
            cd "$SCRIPT_DIR/AccountLevel"
            
            if sam deploy --config-env main --no-confirm-changeset; then
                log_success "AccountLevel infrastructure updated with container security groups"
            else
                log_error "AccountLevel update failed"
                exit 1
            fi
            
            cd "$SCRIPT_DIR"
        else
            log_success "Container security groups already exist"
        fi
    else
        log_info "Deploying new AccountLevel infrastructure..."
        cd "$SCRIPT_DIR/AccountLevel"
        
        if sam deploy --config-env main --no-confirm-changeset; then
            log_success "AccountLevel infrastructure deployed successfully"
        else
            log_error "AccountLevel deployment failed"
            exit 1
        fi
        
        cd "$SCRIPT_DIR"
    fi
}

# Get AccountLevel stack outputs
get_account_level_outputs() {
    log_info "Getting AccountLevel stack outputs..."
    
    local stack_name="R4B-VPC-Main"  # Use existing VPC stack name
    local region="us-west-1"
    
    # Get VPC ID
    VPC_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='VPCId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    # Get Subnet IDs
    PUBLIC_SUBNET_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='PublicSubnetId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    PRIVATE_SUBNET_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet1Id'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    # Get Security Group IDs
    ALB_SG_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ALBSecurityGroupId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    PUBLIC_SERVICES_SG_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='PublicServicesSecurityGroupId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    PRIVATE_SERVICES_SG_ID=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='PrivateServicesSecurityGroupId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$VPC_ID" && -n "$PUBLIC_SUBNET_ID" && -n "$PRIVATE_SUBNET_ID" ]]; then
        log_success "AccountLevel outputs retrieved successfully"
        log_info "VPC ID: $VPC_ID"
        log_info "Public Subnet: $PUBLIC_SUBNET_ID"
        log_info "Private Subnet: $PRIVATE_SUBNET_ID"
    else
        log_error "Failed to retrieve AccountLevel outputs. Make sure AccountLevel stack is deployed."
        exit 1
    fi
}

# Deploy Application infrastructure
deploy_application() {
    log_info "Deploying Application infrastructure (ECS, ALB, Services)..."
    
    log_info "Using existing VPC infrastructure from R4B-VPC-Main stack"
    log_info "VPC ID: $VPC_ID"
    log_info "Public Subnet: $PUBLIC_SUBNET_ID"
    log_info "Private Subnet: $PRIVATE_SUBNET_ID"
    
    if sam deploy --config-env "$STAGE" --no-confirm-changeset; then
        log_success "Application infrastructure deployed successfully"
    else
        log_error "Application deployment failed"
        exit 1
    fi
}

# Delete infrastructure
delete_infrastructure() {
    log_warning "Deleting $STAGE infrastructure..."
    read -p "Are you sure you want to delete the $STAGE environment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deletion cancelled"
        exit 0
    fi
    
    local app_stack_name="R4B-OpActive-App-${STAGE^}"
    local vpc_stack_name="R4B-OpActive-VPC-${STAGE^}"
    
    # Delete Application stack first
    log_info "Deleting Application stack: $app_stack_name"
    if aws cloudformation delete-stack --stack-name "$app_stack_name" --region us-west-1; then
        log_info "Waiting for Application stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$app_stack_name" --region us-west-1
        log_success "Application stack deleted"
    else
        log_warning "Application stack deletion failed or stack doesn't exist"
    fi
    
    # Delete AccountLevel stack
    log_info "Deleting AccountLevel stack: $vpc_stack_name"
    if aws cloudformation delete-stack --stack-name "$vpc_stack_name" --region us-west-1; then
        log_info "Waiting for AccountLevel stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$vpc_stack_name" --region us-west-1
        log_success "AccountLevel stack deleted"
    else
        log_warning "AccountLevel stack deletion failed or stack doesn't exist"
    fi
    
    log_success "Infrastructure deletion completed"
}

# Display deployment information
show_deployment_info() {
    log_info "Retrieving deployment information..."
    
    local app_stack_name="R4B-OpActive-App-${STAGE^}"
    local region="us-west-1"
    
    # Get Application URL
    local app_url=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ApplicationURL'].OutputValue" \
        --output text 2>/dev/null || echo "Not available")
    
    # Get API URL
    local api_url=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='APIURL'].OutputValue" \
        --output text 2>/dev/null || echo "Not available")
    
    # Get Dashboard URL
    local dashboard_url=$(aws cloudformation describe-stacks \
        --stack-name "$app_stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='CloudWatchDashboardURL'].OutputValue" \
        --output text 2>/dev/null || echo "Not available")
    
    echo
    log_success "=== DEPLOYMENT COMPLETE ==="
    echo -e "${GREEN}Environment:${NC} $STAGE"
    echo -e "${GREEN}Application URL:${NC} $app_url"
    echo -e "${GREEN}API Documentation:${NC} $api_url"
    echo -e "${GREEN}CloudWatch Dashboard:${NC} $dashboard_url"
    echo
    log_info "Next steps:"
    echo "1. Build and push Docker images: ./build-containers.sh $STAGE"
    echo "2. Run verification tests: ./verify-deployment.sh $STAGE"
    echo "3. Monitor services: $dashboard_url"
    echo
}

# Main execution flow
main() {
    echo "=== OpActive R4B Infrastructure Deployment ==="
    echo "Stage: $STAGE"
    echo "Action: $ACTION"
    echo
    
    validate_inputs
    check_prerequisites
    
    case "$ACTION" in
        "validate")
            validate_templates
            log_success "Validation completed successfully"
            ;;
        "deploy")
            validate_templates
            deploy_account_level
            get_account_level_outputs
            deploy_application
            show_deployment_info
            ;;
        "delete")
            delete_infrastructure
            ;;
    esac
}

# Run main function
main "$@"
