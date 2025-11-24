<!--
 Copyright 2022 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

# AI-Powered Lecture Management System Backend

This project is a FastAPI-based backend for an AI-powered Lecture system, providing features for course management, exam generation, and content analysis.

The lecture-backend is designed to handle various aspects of course management, including user authentication, course creation, exam generation, and content analysis using AI technologies. It integrates with AWS services for storage, transcription, and AI processing.

## Repository Structure

The repository is organized as follows:

- `alembic/`: Database migration scripts and configuration
- `database/`: Database models, schemas, and CRUD operations
- `function/`: Core functionality modules
  - `content_query/`: Content querying utilities
  - `exam_generator/`: Exam generation logic
  - `llms/`: Language model integration (Bedrock, OpenAI)
  - `rubric/`: Rubric-related functionality
  - `transcribe/`: Audio transcription utilities
- `routers/`: API route definitions
- `utility/`: Utility functions and helpers
- `main.py`: Application entry point
- `Dockerfile`: Container definition for the application
- `requirements.txt`: Python dependencies (if not using Poetry)
- `pyproject.toml`: Poetry configuration file
- `poetry.lock`: Poetry lock file for reproducible builds
- `buildspec.yml`: AWS CodeBuild configuration

Key files:

- `main.py`: FastAPI application setup and main routes
- `database/models.py`: SQLAlchemy ORM models
- `database/schemas.py`: Pydantic schemas for request/response validation
- `utility/aws.py`: AWS service integrations
- `utility/auth.py`: Authentication and authorization utilities

## Usage Instructions

### Installation

Prerequisites:

- Python 3.9+
- Docker (optional, for containerized deployment)
- AWS account with necessary permissions
- Poetry (optional if you want to use Poetry for dependency management)

1. Clone the repository:

   ```
   git clone <repository_url>
   cd lecture-backend
   ```

2. Install dependencies:

   #### If using Poetry (recommended):

   - Install Poetry (if you don't have it already):

     ```
     curl -sSL https://install.python-poetry.org | python3 -
     ```

   - Install project dependencies using Poetry:
     ```
     poetry install
     ```

   #### Alternatively, if using `requirements.txt`:

   - Install dependencies using pip:
     ```
     pip install -r requirements.txt
     ```

3. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:
   ```
   DATABASE_URL=<your_database_url>
   AWS_REGION_NAME=<your_aws_region>
   AWS_S3_AUDIO_BUCKET_NAME=<your_s3_audio_bucket>
   AWS_S3_CONTENT_BUCKET_NAME=<your_s3_content_bucket>
   COGNITO_USERPOOL_ID=<your_cognito_user_pool_id>
   COGNITO_APP_CLIENT_ID=<your_cognito_app_client_id>
   ```

### Running the Application

1. Start the FastAPI server:

   #### If using Poetry:

   ```
   poetry run uvicorn main:app --reload
   ```

   #### If using `requirements.txt`:

   ```
   uvicorn main:app --reload
   ```

2. Access the API documentation at `http://localhost:8000/docs`

### Docker Deployment

1. Build the Docker image:

   ```
   docker build -t lecture-backend .
   ```

2. Run the container:
   ```
   docker run -p 8000:8000 --env-file .env lecture-backend
   ```

### Database Migrations

To apply database migrations:

```
alembic upgrade head
```

To create a new migration:

```
alembic revision -m "Description of changes"
```

### Testing & Quality

Run tests using pytest:

```
pytest
```

### Troubleshooting

Common issues:

1. **Database connection errors**:

   - Ensure the `DATABASE_URL` in your `.env` file is correct.
   - Check that the database server is running and accessible.
   - Verify network settings if using a remote database.

2. **AWS credential issues**:

   - Ensure AWS credentials are properly configured in your environment or AWS CLI.
   - Verify that the IAM user/role has the necessary permissions for S3, Cognito, and other AWS services used.

3. **Cognito authentication failures**:

   - Double-check the `COGNITO_USERPOOL_ID` and `COGNITO_APP_CLIENT_ID` in your `.env` file.
   - Ensure the Cognito user pool is properly configured with the correct app client settings.

For verbose logging, set the `LOG_LEVEL` environment variable to `DEBUG`:

```
export LOG_LEVEL=DEBUG
```

## Dependency Management with Poetry

This project uses **Poetry** for managing dependencies. Poetry helps ensure that all developers use the same versions of dependencies and allows for easy management of virtual environments.

### Setting Up Poetry

1. **Install Poetry**:  
   If you don't already have Poetry installed, you can install it using the following command:

   ```
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies**:  
   Once Poetry is installed, you can install all the dependencies (both for production and development) by running:

   ```
   poetry install
   ```

3. **Adding dependencies**:  
   To add a new dependency, use the following command:

   ```
   poetry add <package-name>
   ```

   For example:

   ```
   poetry add fastapi
   ```

4. **Adding development dependencies**:  
   To add a development dependency (e.g., testing libraries), use the `--dev` flag:

   ```
   poetry add --dev pytest
   ```

5. **Updating dependencies**:  
   To update all dependencies to their latest compatible versions, use:

   ```
   poetry update
   ```

6. **Locking dependencies**:  
   The `poetry.lock` file ensures that all installations use the same versions of dependencies. When you install or update dependencies, Poetry will automatically update this lock file.

### Running the Application with Poetry

To run the FastAPI server using Poetry, use:

```
poetry run uvicorn main:app --reload
```

### Running Tests with Poetry

To run tests using pytest with Poetry, use:

```
poetry run pytest
```

## Data Flow

The lecture-backend processes requests through the following flow:

1. Client sends a request to a FastAPI endpoint
2. FastAPI router handles the request and performs authentication/authorization
3. The appropriate service function is called, which may interact with:
   - Database (via SQLAlchemy ORM)
   - AWS services (S3, Cognito, Transcribe, etc.)
   - AI models (via Bedrock or OpenAI)
4. Results are processed and returned to the client

```
[Client] -> [FastAPI Router] -> [Service Function]
                                       |
                                       v
                     [Database] <-> [AWS Services] <-> [AI Models]
                                       |
                                       v
                            [Processed Results]
                                       |
                                       v
                               [Client Response]
```

## SQLAlchemy Async Operations Guide

This guide explains the two main approaches for database operations in SQLAlchemy and when to use each one.

### Modern Async Style (SQLAlchemy 2.0)

This is the recommended approach for new async endpoints:

```python
async def get_items(db: AsyncSession, ...):
    stmt = select(YourModel).where(YourModel.field == value)
    result = await db.execute(stmt)
    return result.scalars().all()  # or .first() for single result
```

Key features:
- Uses `AsyncSession` for async operations
- Explicit `select()` and `where()` syntax
- Better query optimization
- Designed for async/await
- More explicit and easier to debug

### Classic Style (SQLAlchemy 1.x)

This approach is used for synchronous operations:

```python
def get_items(db: Session, ...):
    return db.query(YourModel).filter(YourModel.field == value).first()
```

Key features:
- Uses `Session` for sync operations
- Uses `query()` and `filter()` methods
- Simpler syntax but less explicit
- Not designed for async operations

### Common Patterns

```python
# Get single record
stmt = select(YourModel).where(YourModel.id == id)
result = await db.execute(stmt)
item = result.scalar_one_or_none()

# Get multiple records
stmt = select(YourModel).where(YourModel.field == value)
result = await db.execute(stmt)
items = result.scalars().all()

# Load relationships
stmt = select(YourModel).options(
    selectinload(YourModel.relationship)
).where(...)
```

### Best Practices

1. **Session Types**:
   - Use `AsyncSession` with async functions
   - Use `Session` with sync functions
   - Never mix session types

2. **Query Style**:
   - Prefer modern style (select/where) over classic (query/filter)
   - Use `scalar_one_or_none()` instead of `first()`
   - Always handle errors with try/except

3. **Async Endpoints**:
```python
@app.get("/your-endpoint")
async def your_endpoint(
    db: AsyncSession = Depends(get_async_db)
):
    try:
        async with db.begin():
            # Your async database operations here
            pass
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error")
```

4. **Sync Endpoints**:
```python
@app.get("/your-endpoint")
def your_endpoint(
    db: Session = Depends(get_db)
):
    try:
        # Your sync database operations here
        pass
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Database error")
```

## Deployment

Prerequisites:

- AWS account with ECR repository
- EC2 instance with Docker installed
- IAM role with necessary permissions attached to the EC2 instance

Deployment steps:

1. Build and push the Docker image to ECR:

   ```
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com
   docker build -t <ecr_repository_uri> .
   docker push <ecr_repository_uri>
   ```

2. SSH into the EC2 instance and pull the latest image:

   ```
   docker pull <ecr_repository_uri>:latest
   ```

3. Stop the existing container and start a new one with the updated image:

   ```
   docker stop edt-ai-translator
   docker rm edt-ai-translator
   docker run -d --name edt-ai-translator -p 8000:8000 --env-file /path/to/.env -v /data/translator:/app/data <ecr_repository_uri>:latest
   ```

4. Run database migrations:
   ```
   docker exec edt-ai-translator alembic upgrade head
   ```

## Infrastructure

The lecture-backend relies on the following AWS infrastructure:

- ECR (Elastic Container Registry):

  - Repository: `444208416329.dkr.ecr.eu-central-1.amazonaws.com/edt-ai-translator`

- EC2:

  - Instance ID: `i-0a569c1a4a95752b5`
  - Purpose: Hosts the Docker container running the application

- RDS (Relational Database Service):

  - Endpoint: `lecture.cvcvaal1vwd4.eu-central-1.rds.amazonaws.com`
  - Database: `lecture_core`

- S3:

  - Bucket (Audio): `lecture-audiofiles`
  - Bucket (Content): `lecture-content`

- Cognito:

  - User Pool ID: `eu-central-1_4jrcqhf3g`
  - App Client ID: `XXXXXXXXXXXXXXXXXXXXXXXXX`

- IAM:
  - User: `XXXXXXXXXXXXXXXXXXXX`
  - Purpose: Provides necessary permissions for AWS service interactions

The infrastructure is managed through a combination of manual setup and AWS CodePipeline for continuous deployment.

## Async Database Operations Guide

This guide explains how to properly implement asynchronous database operations in FastAPI endpoints.

### Required Imports
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import Depends
from database.db import get_async_db
```

### Basic Endpoint Structure
```python
@router.get("/your-endpoint")
async def your_endpoint(
    db: AsyncSession = Depends(get_async_db),  # Always use AsyncSession
    current_user: User = Depends(require_token_types(allowed_types=["cognito"]))  # If authentication is needed
):
    try:
        async with db.begin():  # Always use a transaction context
            # Your code here
            pass
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error")
```

### Database Queries
```python
# ❌ DON'T DO THIS:
user = db.query(User).filter(User.id == user_id).first()  # Synchronous method

# ✅ DO THIS INSTEAD:
stmt = select(User).where(User.id == user_id)
result = await db.execute(stmt)
user = result.scalar_one_or_none()
```

### Loading Relationships
```python
# ❌ DON'T DO THIS:
await db.refresh(user)
await db.refresh(user.group)

# ✅ DO THIS INSTEAD:
stmt = select(User).options(
    selectinload(User.group).selectinload(Group.region)
)
result = await db.execute(stmt)
user = result.scalar_one_or_none()
```

### Complete Example
```python
@router.get("/example")
async def example_endpoint(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_token_types(allowed_types=["cognito"]))
):
    try:
        async with db.begin():
            # 1. Main query
            stmt = select(User).options(
                selectinload(User.group)
            ).where(User.id == current_user.id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # 2. Process data
            return {
                "id": str(user.id),
                "name": user.name,
                "group": {
                    "id": str(user.group.id),
                    "name": user.group.name
                } if user.group else None
            }
            
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error")
```

### Key Points to Remember
- Always use `AsyncSession` instead of `Session`
- Use `async with db.begin()` for transactions
- Use `select()` instead of `query()`
- Use `selectinload` for loading relationships
- Always use `await` with database operations
- Handle errors with try/except
- Convert UUIDs to string in responses
- Use `scalar_one_or_none()` to get a single result

### Common Patterns
```python
# For creating:
new_item = YourModel(**data)
db.add(new_item)
await db.flush()

# For updating:
stmt = select(YourModel).where(YourModel.id == id)
result = await db.execute(stmt)
item = result.scalar_one_or_none()
if item:
    for key, value in data.items():
        setattr(item, key, value)

# For deleting:
stmt = select(YourModel).where(YourModel.id == id)
result = await db.execute(stmt)
item = result.scalar_one_or_none()
if item:
    await db.delete(item)
```

### 📄 License Change (November 24, 2025)

This project was originally released under the **CC BY 4.0** license.  
As of **November 24, 2025**, all source code in this repository is licensed under the **Apache License 2.0**.
