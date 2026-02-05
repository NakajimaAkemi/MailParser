# Email Parser API

FastAPI-based email parsing service using LLM for structured data extraction with Oracle Cloud Infrastructure (OCI).

---

## Prerequisites

* Docker
* Docker Compose
* OCI credentials (config + private key)

---

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
└── app/config/
    ├── config               # OCI config file (includes model and compartment_id)
    └── oci_api_key.pem      # OCI private key
```

---

## Configuration

### OCI Configuration (Local Project)

The project expects the OCI configuration to be located **inside the repository** at:

```
./app/config
```

This directory is mounted into the container at:

```
/app/config
```

Make sure you have:

* `app/config/config` — OCI CLI config file
* `app/config/oci_api_key.pem` — OCI private key

---

### OCI config example (`app/config/config`)

```ini
[DEFAULT]
user=ocid1.user.oc1..xxxxx
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
tenancy=ocid1.tenancy.oc1..xxxxx
region=eu-frankfurt-1
key_file=/app/config/oci_api_key.pem

# LLM specific settings
model=oci/cohere.command-a-03-2025
oci_compartment_id=ocid1.compartment.oc1..xxxxx
```

### Important Notes

* `key_file` **must** use the container path:

  ```
  /app/config/oci_api_key.pem
  ```
* Do **not** use quotes around `model` and `oci_compartment_id`
* `config.yaml` is **not used**

---

## Building and Running

### Using Docker Compose (Recommended)

```bash
docker-compose up -d --build
```

### View logs

```bash
docker-compose logs -f
```

### Stop the service

```bash
docker-compose down
```

---

## Running with Docker only

```bash
# Build image
docker build -t email-parser-api .

# Run container
docker run -d \
  -p 8000:8000 \
  -v ./app/config:/app/config:ro \
  --name email-parser-api \
  email-parser-api

# Logs
docker logs -f email-parser-api

# Stop & remove
docker stop email-parser-api
docker rm email-parser-api
```

---

## API Usage

### Interactive Documentation

Once running:

* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Endpoints

* `GET /` — Root endpoint
* `GET /health` — Health check
* `POST /parse-email` — Parse email content

---

## Example Request

```bash
curl -X POST "http://localhost:8000/parse-email" \
  -H "Content-Type: application/json" \
  -d '{
    "email_body": "From: john.doe@example.com\nTo: support@company.com\nSubject: Order Issue\nDate: 2024-01-15\n\nHello,\n\nI have an issue with my recent order #12345.\n\nBest regards,\nJohn Doe"
  }'
```

---

## Example Response

```json
{
  "emails": [
    {
      "CUSTOMER_NAME": "John Doe",
      "MAIL_TYPE": "TO",
      "CUSTOMER_OPERATOR": "john.doe@example.com",
      "TOPIC": "Order Issue",
      "MAIL_DATE": "2024-01-15"
    }
  ],
  "FULL_BODY": "Hello,\n\nI have an issue with my recent order #12345.\n\nBest regards,\nJohn Doe"
}
```

---

## Development (Without Docker)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

---

## Security Best Practices

Add to `.gitignore`:

```gitignore
app/config/config
app/config/oci_api_key.pem
```

---

## Troubleshooting

### OCI Authentication Errors

* Check `app/config/config`
* Check `app/config/oci_api_key.pem`
* Verify `key_file=/app/config/oci_api_key.pem`

### Model Not Found

* Verify `model` value
* Check region compatibility

### Compartment Errors

* Verify `oci_compartment_id`
* Check permissions on compartment

---
