"""setup.py controls the build, testing, and distribution of the egg"""
from setuptools import setup, find_packages


def get_requirements():
    """Reads the installation requirements from requirements.txt"""
    with open("requirements.txt") as reqfile:
        return [line for line in reqfile.read().split("\n") if not line.startswith(('#', '-'))]


setup(
    name='flappy_detector',
    description="Lambda project for detecting flappy resources in AWS.",
    packages=find_packages(),
    install_requires=get_requirements(),
    test_suite='nose.collector',
)
