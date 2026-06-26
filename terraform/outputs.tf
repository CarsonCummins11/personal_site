output "editor_url" {
  value       = aws_lambda_function_url.blog_editor.function_url
  description = "URL of the blog post editor"
}
