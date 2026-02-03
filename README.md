# Email Parser API

FastAPI-based email parsing service using LLM for structured data extraction.

## Prerequisites

- Docker and Docker Compose installed
- OCI configuration files (for Oracle Cloud authentication)
- `config.yaml` with model and compartment configuration

## Project Structure

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .dockerignore
├── main.py                  # FastAPI application
├── llm_client.py           # LLM client with OCI integration
├── structured_output.py    # Pydantic models
├── prompt.md               # LLM prompts
├── app/config/            # OCI config directory (to be mounted)
│   ├── config             # OCI config file
│   ├── oci_api_key.pem    # OCI private key
└── └───config.yaml            # Application config
```

## Configuration

### 1. Create `config.yaml`

```yaml
model: "oci/cohere.command-r-plus"  # or your preferred model
oci_compartment_id: "ocid1.compartment.oc1..xxxxx"
```

### 2. Prepare OCI Configuration

Place your OCI configuration files in a `config/` directory:

- `config/config` - OCI CLI config file
- `config/oci_api_key.pem` - Your OCI private key

Example OCI config file:
```
[DEFAULT]
user=ocid1.user.oc1..xxxxx
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
key_file=/app/config/oci_api_key.pem
tenancy=ocid1.tenancy.oc1..xxxxx
region=us-ashburn-1
```

## Building and Running

### Using Docker Compose (Recommended)

```bash
# Build and start the service
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Using Docker directly

```bash
# Build the image
docker build -t email-parser-api .

# Run the container
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  --name email-parser-api \
  email-parser-api

# View logs
docker logs -f email-parser-api

# Stop the container
docker stop email-parser-api
docker rm email-parser-api
```

## API Usage

### Interactive Documentation

Once running, access the interactive API docs at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Example Request

```bash
curl -X POST "http://localhost:8000/parse-email" \
  -H "Content-Type: application/json" \
  -d '{
    "email_body": "From: john.doe@example.com\nTo: support@company.com\nSubject: Order Issue\nDate: 2024-01-15\n\nHello,\n\nI have an issue with my recent order #12345.\n\nBest regards,\nJohn Doe"
  }'
```

### Example Response

```json
{
  "emails": [
    {
      "CUSTOMER_NAME": "John Doe",
      "MAIL_TYPE": "TO",
      "CUSTOMER_OPERATOR": "john.doe@example.com",
      "TOPIC": "Order Issue",
      "MAIL_DATE": "2024-01-15",
      "FULL_BODY": "Hello,\n\nI have an issue with my recent order #12345.\n\nBest regards,\nJohn Doe"
    }
  ]
}
```

## Troubleshooting

### Check if service is running
```bash
docker ps | grep email-parser-api
```

### Check logs
```bash
docker-compose logs -f email-parser-api
```

### Test health endpoint
```bash
curl http://localhost:8000/docs
```

### Common Issues

1. **OCI Authentication Errors**: Verify your OCI config file paths and credentials
2. **Model Not Found**: Check that the model name in `config.yaml` is correct
3. **Port Already in Use**: Change the port mapping in `docker-compose.yml`

## Development

To run locally without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Notes

- The LLMClient initialization in `main.py` needs to be updated to pass the config paths
- Update the `startup_event` function to: `llm = LLMClient(OciPath=Path("config/config"), configPath=Path("config.yaml"))`
