from setuptools import setup, find_packages

setup(
    name="voice-learning",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "Flask==3.0.2",
        "SQLAlchemy==2.0.27",
        "twilio==9.0.0",
        "openai==1.12.0",
        "APScheduler==3.10.4",
        "Flask-WTF==1.2.1",
        "pytest==8.0.2",
        "factory-boy==3.3.0",
        "python-dotenv==1.0.1",
        "gunicorn==21.2.0",
        "passlib[bcrypt]==1.7.4"
    ],
    python_requires=">=3.12",
) 