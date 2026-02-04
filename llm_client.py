from structured_output import ParsedEmailList,EmailRequest
from pathlib import Path
import litellm 
from litellm import completion
from oci.signer import Signer
from oci.config import from_file
from typing import Optional
import json
import os
import re

class LLMClient:
    def __init__(self, OciPath:Path):
        os.environ["OCI_CONFIG_FILE"] = str(OciPath)
        os.environ["OCI_CLI_PROFILE"] = "DEFAULT"
        self.config = from_file()
        self.Signer=Signer(
            tenancy=self.config["tenancy"],
            user=self.config["user"],
            fingerprint=self.config["fingerprint"],
            private_key_file_location=self.config["key_file"],
            pass_phrase=self.config.get("pass_phrase", None),
        )
        self.model=self.config["model"]
        self.oci_compartment_id = self.config["oci_compartment_id"]
        print(f"Model: {self.model}")
        print(f"OCI Compartment ID: {self.oci_compartment_id}")
        
    def _clean_json_response(self, content: str) -> str:
        """Clean up JSON response by extracting valid JSON"""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # Try to find JSON object or array
        # Look for content between outermost { } or [ ]
        brace_start = content.find("{")
        bracket_start = content.find("[")

        # Determine which comes first
        if brace_start == -1:
            start = bracket_start
        elif bracket_start == -1:
            start = brace_start
        else:
            start = min(brace_start, bracket_start)

        if start == -1:
            return content

        # Find matching closing character
        if content[start] == "{":
            # Find the last closing brace
            depth = 0
            for i in range(start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return content[start : i + 1].strip()
        else:
            # Find the last closing bracket
            depth = 0
            for i in range(start, len(content)):
                if content[i] == "[":
                    depth += 1
                elif content[i] == "]":
                    depth -= 1
                    if depth == 0:
                        return content[start : i + 1].strip()

        return content.strip()


    def fetch_prompt(self,prompt_path: Path, section: Optional[str] = None, **kwargs) -> str:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract specific section if requested
        if section:
            content = self._extract_section(content, section)

        # Inject variables
        if kwargs:
            content = content.format(**kwargs)

        return content    


    def _extract_section(self,content: str, section_name: str) -> str:
        """
        Extract a specific section from markdown content by header name.
        Supports ## headers at any level.

        Args:
            content: Full markdown content
            section_name: Header name to find (without ## prefix)

        Returns:
            Content of the section (excluding the header itself)

        Raises:
            ValueError: If section is not found
        """
        lines = content.split("\n")
        section_lines = []
        in_section = False
        section_level = None

        for line in lines:
            # Check if this is a header line
            if line.strip().startswith("#"):
                # Parse header level and title
                header_match = line.strip().lstrip("#")
                header_level = len(line.strip()) - len(header_match)
                header_title = header_match.strip()

                # Check if this is our target section
                if header_title.lower() == section_name.lower():
                    in_section = True
                    section_level = header_level
                    continue  # Skip the header itself

                # If we're in a section and hit a same/higher level header, we're done
                elif in_section and header_level <= section_level:
                    break

            # Collect lines if we're in the target section
            if in_section:
                section_lines.append(line)

        if not section_lines:
            raise ValueError(f"Section '{section_name}' not found in markdown file")

        return "\n".join(section_lines).strip()


    def extract_first_email(self,raw_email: str) -> str:
        """
        Returns the first (latest) email including headers and body.
        Attachments, base64 blobs, and quoted messages are removed.
        """

        # 1. Split headers and body
        parts = raw_email.split("\n\n", 1)
        headers = parts[0]
        body = parts[1] if len(parts) > 1 else ""

        # 2. Remove MIME/base64 noise
        body = re.sub(
            r"Content-Transfer-Encoding:\s*base64.*?={2,}",
            "",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )

        body = re.sub(
            r"Content-Type:\s*(image|application)/.*?(\n\n|\Z)",
            "",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # 3. Cut quoted replies (English + Italian + Outlook)
        quote_markers = [
            r"^On .* wrote:.*",
            r"^Il .* ha scritto:.*",
            r"^-{2,}\s*Original Message\s*-{2,}",
            r"^From:.*\nSent:.*",
            r"^Da:.*\nInviato:.*",
        ]

        for marker in quote_markers:
            body = re.split(marker, body, flags=re.IGNORECASE | re.MULTILINE)[0]

        # 4. Remove signatures
        body = re.split(r"\n--\s*\n", body)[0]

        # 5. Normalize whitespace
        body = re.sub(r"\n{3,}", "\n\n", body).strip()

        # 6. Return headers + cleaned body
        return f"{headers.strip()}\n\n{body}"


    def complete(self, email: EmailRequest, max_retries=3) -> ParsedEmailList:
        """
        Parse the email body using LLM.
        
        Args:
            email: EmailRequest object containing the email_body
            max_retries: Maximum number of retry attempts
            
        Returns:
            ParsedEmailList: Structured parsed email data
        """
        # Extract the actual email string from the EmailRequest object
        mail = self.extract_first_email(email.email_body)
        
        # Fetch prompts
        prompt = self.fetch_prompt(Path("prompt.md"), "MAIL PARSER", email=mail)
        pydantic_portion = self.fetch_prompt(
            Path("prompt.md"), 
            "Pydantic", 
            format=json.dumps(ParsedEmailList.model_json_schema(), indent=2)
        )
        final_prompt = prompt + "\n\n" + pydantic_portion
        
        messages = [{"role": "user", "content": final_prompt}]
        
        for i in range(max_retries):
            print(f"Attempt {i + 1}/{max_retries}")
            try:
                response = completion(
                    model=self.model,
                    messages=messages,
                    oci_signer=self.Signer,
                    oci_region=self.config["region"],
                    oci_compartment_id=self.oci_compartment_id
                )
                
                content_cleaned = self._clean_json_response(
                    response["choices"][0]["message"]["content"]
                )
                json_data = json.loads(content_cleaned)
                result = ParsedEmailList.model_validate(json_data)
                print(f"Successfully parsed email on attempt {i + 1}")
                return result
                
            except Exception as e:
                print(f"Error on attempt {i + 1}: {e}")
                if i < max_retries - 1:  # Don't append error on last attempt
                    messages.append({
                        "role": "assistant", 
                        "content": "I encountered an error. Let me try again."
                    })
                    messages.append({
                        "role": "user", 
                        "content": f"Previous attempt failed with error: {str(e)}. Please provide valid JSON matching the schema."
                    })
        
        print(f"Failed to parse email after {max_retries} attempts")
        return None