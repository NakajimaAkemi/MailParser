from pydantic import BaseModel, Field, EmailStr
from typing import List, Literal

# Pydantic model for a single parsed email
class ParsedEmail(BaseModel):
    CUSTOMER_NAME: str = Field(..., description="Name of the customer")
    MAIL_TYPE: Literal["TO", "CC", "BCC"] = Field(..., description="Type of email recipient (TO, CC, or BCC)")
    CUSTOMER_OPERATOR: str = Field(..., description="Email address of the customer")
    TOPIC: str = Field(..., description="Topic of the email")
    MAIL_DATE: str = Field(..., description="Date of the email in YYYY-MM-DD format")
    

class ParsedEmailList(BaseModel):
    emails: List[ParsedEmail] = Field(..., description="List of parsed email entries")
    FULL_BODY: str = Field(..., description="Full body content of the email")

    
class EmailRequest(BaseModel):
    email_body: str = Field(..., description="Full raw email body to parse")
    


