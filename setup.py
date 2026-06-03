from setuptools import find_packages, setup


setup(
    name="hermes-kb",
    version="0.1.0",
    description="Knowledge base sync skeleton for GitLab -> Hermes -> Embedding -> Qdrant",
    packages=find_packages(include=["hermes", "hermes.*"]),
    include_package_data=True,
)
