# networking: one VPC, public subnets in two AZs, an internet gateway, no NAT gateway (M9 Task 9.2).
# Fargate tasks run in the public subnets with a public IP so they can pull from ECR and reach AWS APIs without a
# NAT gateway (~$33/month each) or interface endpoints (~$7/month each). Inbound traffic is still closed by the
# security group (modules/security); nothing listens publicly unless allowed_ingress_cidrs is set.

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name}-igw" }
}

resource "aws_subnet" "public" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.this.id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(var.cidr_block, 8, count.index)
  map_public_ip_on_launch = false # ECS assigns public IPs per service (assign_public_ip); nothing else gets one
  tags                    = { Name = "${var.name}-public-${data.aws_availability_zones.available.names[count.index]}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# CIS AWS 5.4: the default security group allows nothing. Workloads use the explicit groups in modules/security.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name}-default-deny-all" }
}
