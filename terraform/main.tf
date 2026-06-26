terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Bundling — pip-install deps into .build/package, copy lambda_function.py
# ---------------------------------------------------------------------------
# --platform + --only-binary ensures Linux-compatible wheels are downloaded
# even when running terraform apply from macOS.

locals {
  build_dir        = "${path.module}/.build/package"
  requirements_src = "${path.module}/../requirements.txt"
  lambda_src       = "${path.module}/../lambda_function.py"
  editor_html      = "${path.module}/../editor.html"
  editor_css       = "${path.module}/../editor.css"
  editor_js        = "${path.module}/../editor.js"
}

resource "null_resource" "bundle" {
  triggers = {
    requirements_hash = filemd5(local.requirements_src)
    lambda_hash       = filemd5(local.lambda_src)
    html_hash         = filemd5(local.editor_html)
    css_hash          = filemd5(local.editor_css)
    js_hash           = filemd5(local.editor_js)
  }

  provisioner "local-exec" {
    command = <<-EOT
      rm -rf '${local.build_dir}'
      mkdir -p '${local.build_dir}'
      uv pip install \
        --requirement '${local.requirements_src}' \
        --target '${local.build_dir}' \
        --python-version 3.12 \
        --python-platform x86_64-unknown-linux-gnu \
        --only-binary :all:
      cp '${local.lambda_src}' '${local.build_dir}/'
      cp '${local.editor_html}' '${local.build_dir}/'
      cp '${local.editor_css}' '${local.build_dir}/'
      cp '${local.editor_js}' '${local.build_dir}/'
    EOT
  }
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = local.build_dir
  output_path = "${path.module}/.build/lambda.zip"
  depends_on  = [null_resource.bundle]
}

# ---------------------------------------------------------------------------
# IAM
# ---------------------------------------------------------------------------

resource "aws_iam_role" "lambda" {
  name = "blog-editor-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------------------------------------------------------------------------
# Lambda + function URL
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "blog_editor" {
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  function_name    = "blog-editor"
  role             = aws_iam_role.lambda.arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  timeout          = 30

  environment {
    variables = {
      GITHUB_TOKEN = var.github_token
      REPO_OWNER   = var.repo_owner
      REPO_NAME    = var.repo_name
    }
  }
}

resource "aws_lambda_function_url" "blog_editor" {
  function_name      = aws_lambda_function.blog_editor.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "public_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.blog_editor.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke" {
  statement_id  = "AllowPublicInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.blog_editor.function_name
  principal     = "*"
}
