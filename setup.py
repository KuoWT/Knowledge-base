from setuptools import find_packages, setup


setup(
    name="knowledge-base-api",
    version="0.1.0",
    description="Knowledge base API for GitLab sync, embedding, and Qdrant indexing",
    packages=find_packages(include=["knowledge_base_api", "knowledge_base_api.*"]),
    include_package_data=True,
)
