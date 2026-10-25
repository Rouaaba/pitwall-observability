terraform {
  required_version = ">= 1.17.0"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "6.13.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "4.0.6"
    }
  }

  cloud {
    organization = "formula"
    workspaces {
      name = "pitwall-github"
    }
  }
}

provider "github" {
  owner = var.github_owner
  token = var.github_token
}
