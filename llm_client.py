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
        self.model=f"oci/{self.config["model"]}"
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
    

    def strip_base64_attachments(self,email_raw):
        """
        Rimuove allegati base64 in modo robusto.
        Funziona con qualsiasi formato MIME.
        """
        # Pattern: Content-Transfer-Encoding: base64 seguito da dati base64
        # fino al prossimo boundary (che inizia con --)
        pattern = r'(Content-Transfer-Encoding:\s*base64\s*\n)([\s\S]*?)(?=\n--)'
        
        def replace_base64(match):
            header = match.group(1)
            # Conta quante righe di base64 c'erano
            base64_lines = match.group(2).strip().split('\n')
            removed_size = sum(len(line) for line in base64_lines)
            return f"{header}\n[BASE64 REMOVED - {len(base64_lines)} lines, ~{removed_size} bytes]\n"
        
        cleaned = re.sub(pattern, replace_base64, email_raw)
        return cleaned


    def strip_base64_simple(self,email_raw):
        """
        Versione ancora più semplice: rimuove tutto tra 
        'Content-Transfer-Encoding: base64' e il prossimo boundary
        """
        lines = email_raw.split('\n')
        result = []
        skip = False
        removed_lines = 0
        
        for line in lines:
            # Inizia a skippare dopo "Content-Transfer-Encoding: base64"
            if 'Content-Transfer-Encoding: base64' in line:
                result.append(line)
                result.append(f'[BASE64 DATA REMOVED - see next boundary]')
                skip = True
                removed_lines = 0
                continue
            
            # Ferma lo skip al prossimo boundary
            if skip and line.startswith('--'):
                skip = False
                result.append(f'[{removed_lines} lines removed]')
                result.append(line)
                continue
            
            # Skippa le righe base64
            if skip:
                removed_lines += 1
                continue
            
            # Aggiungi tutte le altre righe
            result.append(line)
        
        return '\n'.join(result)


    def clean_email_for_llm(self,email_raw, max_chars=8000):
        """
        Versione completa: rimuove base64 E tronca se necessario
        """
        # Step 1: Rimuovi base64
        cleaned = self.strip_base64_simple(email_raw)
        
        # Step 2: Se ancora troppo grande, tronca
        if len(cleaned) > max_chars:
            lines = cleaned.split('\n')
            
            # Trova dove finiscono gli header
            header_end = 0
            for i, line in enumerate(lines):
                if line.strip() == '' or line.startswith('--'):
                    header_end = i
                    break
            
            # Mantieni header completi
            header = '\n'.join(lines[:header_end + 5])
            
            # Prendi solo prime righe del body
            remaining_chars = max_chars - len(header)
            body_lines = lines[header_end + 5:]
            
            body = ''
            for line in body_lines:
                if len(body) + len(line) > remaining_chars:
                    break
                body += line + '\n'
            
            cleaned = header + '\n' + body + '\n[...TRUNCATED FOR LENGTH...]'
        
        return cleaned
    



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

        mail = self.clean_email_for_llm(email.email_body,2000)
        print(mail)
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
                return {"emails":result.emails,"EMAIL_BODY":mail}
                
            except Exception as e:
                print(f"Error on attempt {i + 1}: {e}")
                if i < max_retries - 1:  # Don't append error on last attempt
                    print(f"Error {e}")
                    messages.append({
                        "role": "user", 
                        "content": f"Previous attempt failed with error: {str(e)}. Please provide valid JSON matching the schema."
                    })
        
        print(f"Failed to parse email after {max_retries} attempts")
        return None