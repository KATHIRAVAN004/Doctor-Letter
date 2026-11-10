"""Extensible letter-type registry.

To add a new letter type, add one entry to LETTER_TYPES:
  - label:  shown in the type picker
  - fields: (name, label, input_type) tuples shown on the form
  - body:   HTML with {{field_name}} placeholders. {{doctor_name}} and
            {{date}} are always available.
"""
from html import escape

LETTER_TYPES = {
        "referral": {
        "label": "Referral Letter",
        "fields": [
            ("consultant_name", "Referred to (Dr.)", "text"),
            ("speciality", "Speciality / Department", "select:Cardiology,Neurology,Orthopedics,Dermatology,ENT,Gynecology,Pediatrics,Psychiatry,General Surgery,General Medicine,Ophthalmology,Urology,Nephrology,Gastroenterology,Oncology,Pulmonology,Endocrinology,Dentistry"),
            ("patient_name", "Patient name", "text"),
            ("patient_age", "Age", "text"),
            ("patient_sex", "Sex", "select:Male,Female,Other"),
            ("reason", "Reason for referral", "textarea"),
        ],
        "body": (
            "<p>Date: {{date}}</p>"
            "<p>To,<br>Dr. {{consultant_name}}<br>{{speciality}}</p>"
            "<p><strong>Re: Referral of {{patient_name}} ({{patient_age}} / {{patient_sex}})</strong></p>"
            "<p>Dear Colleague,</p>"
            "<p>I am referring the above patient for your expert opinion and management. "
            "{{reason}}</p>"
            "<p>Kindly evaluate and advise. Thank you for your help.</p>"
            "<p>Sincerely,<br>Dr. {{doctor_name}}</p>"
        ),
    },
    "medical_certificate": {
        "label": "Medical Certificate",
        "fields": [
            ("patient_name", "Patient name", "text"),
            ("diagnosis", "Diagnosis", "text"),
            ("rest_days", "Days of rest advised", "text"),
            ("from_date", "From date", "date"),
        ],
        "body": (
            "<p>Date: {{date}}</p>"
            "<h3 style='text-align:center'>MEDICAL CERTIFICATE</h3>"
            "<p>This is to certify that <strong>{{patient_name}}</strong> was examined by me "
            "and is diagnosed with {{diagnosis}}. The patient is advised rest for "
            "{{rest_days}} day(s) starting from {{from_date}}.</p>"
            "<p>Dr. {{doctor_name}}</p>"
        ),
    },
    "fitness": {
        "label": "Fitness Certificate",
        "fields": [
            ("patient_name", "Patient name", "text"),
            ("purpose", "Purpose (job / sports / travel)", "text"),
        ],
        "body": (
            "<p>Date: {{date}}</p>"
            "<h3 style='text-align:center'>FITNESS CERTIFICATE</h3>"
            "<p>This is to certify that <strong>{{patient_name}}</strong> has been examined "
            "and found medically fit for {{purpose}}.</p>"
            "<p>Dr. {{doctor_name}}</p>"
        ),
    },
}


def render_body(letter_type: str, values: dict) -> str:
    """Fill placeholders with HTML-escaped values."""
    body = LETTER_TYPES[letter_type]["body"]
    for key, val in values.items():
        body = body.replace("{{%s}}" % key, escape(val or "").replace("\n", "<br>"))
    return body
