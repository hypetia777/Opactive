#!/bin/bash

# =============================================================================
# OpActive R4B Container Build and Push Script
# =============================================================================
# PHASE 3: CONTAINER INFRASTRUCTURE
# This script builds and pushes all 5 container images to ECR
# 
# Usage: ./build-containers.sh [stage] [action] [service]
# stage: demo|dev|staging|prod (default: demo)
# action: build|push|build-push (default: build-push)
# service: bls|salary|fastapi|streamlit|scraping|all (default: all)
#
# Examples:
#   ./build-containers.sh demo build-push        # Build and push all containers for demo
#   ./build-containers.sh prod build fastapi     # Only build FastAPI container for prod
#   ./build-containers.sh dev push streamlit     # Only push Streamlit container for dev
# =============================================================================

set -e

# Default values
STAGE=${1:-demo}
ACTION=${2:-build-push}
SERVICE=${3:-all}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINERS_DIR="$SCRIPT_DIR/../../containers"

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
    
    if [[ ! "$ACTION" =~ ^(build|push|build-push)$ ]]; then
        log_error "Invalid action: $ACTION. Must be one of: build, push, build-push"
        exit 1
    fi
    
    if [[ ! "$SERVICE" =~ ^(bls|salary|fastapi|streamlit|scraping|all)$ ]]; then
        log_error "Invalid service: $SERVICE. Must be one of: bls, salary, fastapi, streamlit, scraping, all"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is required but not installed"
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is required but not installed"
        exit 1
    fi
    
    # Check Docker daemon
    if ! docker ps &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    
    # Check containers directory
    if [[ ! -d "$CONTAINERS_DIR" ]]; then
        log_error "Containers directory not found: $CONTAINERS_DIR"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Get ECR repository URIs from CloudFormation
get_ecr_repositories() {
    log_info "Getting ECR repository URIs from CloudFormation..."
    
    local stack_name="R4B-OpActive-App-${STAGE^}"
    local region="us-west-1"
    
    # Get repository URIs
    BLS_REPO_URI=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='BLSRepositoryURI'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    SALARY_REPO_URI=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='SalaryRepositoryURI'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    FASTAPI_REPO_URI=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='FastAPIRepositoryURI'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    STREAMLIT_REPO_URI=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='StreamlitRepositoryURI'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    SCRAPING_REPO_URI=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query "Stacks[0].Outputs[?OutputKey=='ScrapingRepositoryURI'].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [[ -z "$BLS_REPO_URI" || -z "$SALARY_REPO_URI" || -z "$FASTAPI_REPO_URI" || -z "$STREAMLIT_REPO_URI" || -z "$SCRAPING_REPO_URI" ]]; then
        log_error "Failed to retrieve ECR repository URIs. Make sure the application stack is deployed."
        exit 1
    fi
    
    log_success "ECR repository URIs retrieved successfully"
    log_info "BLS: ${BLS_REPO_URI}"
    log_info "Salary: ${SALARY_REPO_URI}"
    log_info "FastAPI: ${FASTAPI_REPO_URI}"
    log_info "Streamlit: ${STREAMLIT_REPO_URI}"
    log_info "Scraping: ${SCRAPING_REPO_URI}"
}

# Login to ECR
ecr_login() {
    log_info "Logging into ECR..."
    
    local region="us-west-1"
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    
    if aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${region}.amazonaws.com"; then
        log_success "ECR login successful"
    else
        log_error "ECR login failed"
        exit 1
    fi
}

# Build a container image
build_container() {
    local service_name=$1
    local dockerfile_path=$2
    local image_tag=$3
    local build_context=$4
    
    log_info "Building $service_name container..."
    
    # Generate build arguments based on stage
    local build_args=""
    case "$STAGE" in
        "prod")
            build_args="--build-arg ENV=production"
            ;;
        "staging")
            build_args="--build-arg ENV=staging"
            ;;
        "dev")
            build_args="--build-arg ENV=development"
            ;;
        "demo")
            build_args="--build-arg ENV=demo"
            ;;
    esac
    
    # Build with platform specification for compatibility
    if docker build \
        --platform linux/amd64 \
        $build_args \
        -t "$image_tag" \
        -f "$dockerfile_path" \
        "$build_context"; then
        log_success "$service_name container built successfully: $image_tag"
    else
        log_error "$service_name container build failed"
        return 1
    fi
}

# Push a container image
push_container() {
    local service_name=$1
    local image_tag=$2
    
    log_info "Pushing $service_name container to ECR..."
    
    if docker push "$image_tag"; then
        log_success "$service_name container pushed successfully: $image_tag"
    else
        log_error "$service_name container push failed"
        return 1
    fi
}

# Build and/or push BLS server
handle_bls_service() {
    local image_tag="${BLS_REPO_URI}:latest"
    local service_dir="$CONTAINERS_DIR/bls-server"
    
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_container "BLS Server" "$service_dir/Dockerfile" "$image_tag" "$service_dir"
    fi
    
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        push_container "BLS Server" "$image_tag"
    fi
}

# Build and/or push Salary server
handle_salary_service() {
    local image_tag="${SALARY_REPO_URI}:latest"
    local service_dir="$CONTAINERS_DIR/salary-server"
    
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_container "Salary Server" "$service_dir/Dockerfile" "$image_tag" "$service_dir"
    fi
    
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        push_container "Salary Server" "$image_tag"
    fi
}

# Build and/or push FastAPI server
handle_fastapi_service() {
    local image_tag="${FASTAPI_REPO_URI}:latest"
    local service_dir="$CONTAINERS_DIR/fastapi-server"
    
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_container "FastAPI Server" "$service_dir/Dockerfile" "$image_tag" "$service_dir"
    fi
    
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        push_container "FastAPI Server" "$image_tag"
    fi
}

# Build and/or push Streamlit UI
handle_streamlit_service() {
    local image_tag="${STREAMLIT_REPO_URI}:latest"
    local service_dir="$CONTAINERS_DIR/streamlit-ui"
    
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_container "Streamlit UI" "$service_dir/Dockerfile" "$image_tag" "$service_dir"
    fi
    
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        push_container "Streamlit UI" "$image_tag"
    fi
}

# Build and/or push Scraping server
handle_scraping_service() {
    local image_tag="${SCRAPING_REPO_URI}:latest"
    local service_dir="$CONTAINERS_DIR/scraping-server"
    
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_container "Scraping Server" "$service_dir/Dockerfile" "$image_tag" "$service_dir"
    fi
    
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        push_container "Scraping Server" "$image_tag"
    fi
}

# Build Docker Compose compatibility layer
build_compose_compatibility() {
    log_info "Creating Docker Compose compatibility tags..."
    
    # Tag images with docker-compose compatible names for local testing
    docker tag "${BLS_REPO_URI}:latest" "r4b-opactive-bls-server:latest" 2>/dev/null || true
    docker tag "${SALARY_REPO_URI}:latest" "r4b-opactive-salary-server:latest" 2>/dev/null || true
    docker tag "${FASTAPI_REPO_URI}:latest" "r4b-opactive-fastapi-server:latest" 2>/dev/null || true
    docker tag "${STREAMLIT_REPO_URI}:latest" "r4b-opactive-streamlit-ui:latest" 2>/dev/null || true
    docker tag "${SCRAPING_REPO_URI}:latest" "r4b-opactive-scraping-server:latest" 2>/dev/null || true
    
    log_success "Docker Compose compatibility tags created"
}

# Clean up local images (optional)
cleanup_local_images() {
    read -p "Do you want to remove local images to save space? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning up local images..."
        
        docker rmi "${BLS_REPO_URI}:latest" 2>/dev/null || true
        docker rmi "${SALARY_REPO_URI}:latest" 2>/dev/null || true
        docker rmi "${FASTAPI_REPO_URI}:latest" 2>/dev/null || true
        docker rmi "${STREAMLIT_REPO_URI}:latest" 2>/dev/null || true
        docker rmi "${SCRAPING_REPO_URI}:latest" 2>/dev/null || true
        
        log_success "Local images cleaned up"
    else
        log_info "Local images preserved"
    fi
}

# Force ECS service update to pull new images
force_ecs_update() {
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        read -p "Do you want to force ECS services to update with new images? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Forcing ECS service updates..."
            
            local cluster_name="R4B-OpActive-${STAGE}-cluster"
            local region="us-west-1"
            local services=()
            
            case "$SERVICE" in
                "bls")
                    services=("bls-service")
                    ;;
                "salary")
                    services=("salary-service")
                    ;;
                "fastapi")
                    services=("fastapi-service")
                    ;;
                "streamlit")
                    services=("streamlit-service")
                    ;;
                "scraping")
                    services=("scraping-service")
                    ;;
                "all")
                    services=("bls-service" "salary-service" "fastapi-service" "streamlit-service" "scraping-service")
                    ;;
            esac
            
            for service in "${services[@]}"; do
                log_info "Updating $service..."
                if aws ecs update-service \
                    --cluster "$cluster_name" \
                    --service "$service" \
                    --force-new-deployment \
                    --region "$region" > /dev/null; then
                    log_success "$service update initiated"
                else
                    log_warning "$service update failed (service may not exist yet)"
                fi
            done
            
            log_success "ECS service updates initiated"
            log_info "Monitor deployment progress in AWS Console or with: aws ecs describe-services --cluster $cluster_name --services [service-name]"
        fi
    fi
}

# Display build summary
show_build_summary() {
    echo
    log_success "=== BUILD SUMMARY ==="
    echo -e "${GREEN}Stage:${NC} $STAGE"
    echo -e "${GREEN}Action:${NC} $ACTION"
    echo -e "${GREEN}Service:${NC} $SERVICE"
    echo
    
    case "$ACTION" in
        "build")
            log_info "Container images built locally. Use 'push' or 'build-push' to deploy to ECR."
            ;;
        "push")
            log_info "Container images pushed to ECR. Services will pull new images on next deployment."
            ;;
        "build-push")
            log_info "Container images built and pushed to ECR successfully."
            ;;
    esac
    
    echo
    log_info "Next steps:"
    
    if [[ "$ACTION" == "build" ]]; then
        echo "1. Test locally: cd $CONTAINERS_DIR && docker-compose up"
        echo "2. Push to ECR: ./build-containers.sh $STAGE push $SERVICE"
    elif [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        echo "1. Verify deployment: ./verify-deployment.sh $STAGE"
        echo "2. Check application: aws cloudformation describe-stacks --stack-name R4B-OpActive-App-${STAGE^}"
    fi
    echo
}

# Main execution
main() {
    echo "=== OpActive R4B Container Build & Push ==="
    echo "Stage: $STAGE"
    echo "Action: $ACTION"
    echo "Service: $SERVICE"
    echo
    
    validate_inputs
    check_prerequisites
    
    # Only get ECR repos and login if we need to push
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        get_ecr_repositories
        ecr_login
    fi
    
    # Handle specific service or all services
    case "$SERVICE" in
        "bls")
            handle_bls_service
            ;;
        "salary")
            handle_salary_service
            ;;
        "fastapi")
            handle_fastapi_service
            ;;
        "streamlit")
            handle_streamlit_service
            ;;
        "scraping")
            handle_scraping_service
            ;;
        "all")
            handle_bls_service
            handle_salary_service
            handle_fastapi_service
            handle_streamlit_service
            handle_scraping_service
            ;;
    esac
    
    # Create compatibility tags if building
    if [[ "$ACTION" == "build" || "$ACTION" == "build-push" ]]; then
        build_compose_compatibility
    fi
    
    # Offer to force ECS updates
    force_ecs_update
    
    # Offer cleanup
    if [[ "$ACTION" == "push" || "$ACTION" == "build-push" ]]; then
        cleanup_local_images
    fi
    
    # Show summary
    show_build_summary
}

# Run main function
main "$@"
