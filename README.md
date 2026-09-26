# SentinelID 🛡️

## AI-Assisted Fake Identity & Document Screening System

**Smart India Hackathon 2026 \| Software \| Blockchain & Cybersecurity**

> **Tagline:** Detect. Verify. Explain.

------------------------------------------------------------------------

## 1. Problem

Border checkpoints and high-security verification environments process
large numbers of identity and travel documents. Manual verification
requires officers to inspect document information, MRZ data, expiry,
possible tampering, watchlist status, document photographs, and the
person's identity.

The challenge is not only extracting text. The challenge is combining
multiple verification signals into one fast, explainable screening
workflow.

------------------------------------------------------------------------

## 2. Our Solution

**SentinelID** is an AI-assisted identity and document screening
prototype that combines document intelligence, MRZ analysis, validation,
tamper analysis, biometric verification, liveness detection, face
matching, and explainable risk analysis.

### End-to-end pipeline

``` text
Document Image
      ↓
Image Preprocessing
      ↓
OCR Extraction
      ↓
MRZ Detection & Validation
      ↓
Document Validation ─── Database Checks
      ↓
Tamper Detection
      ↓
Document Face Extraction
      ↓
Person Verification
      ↓
Liveness Detection
      ↓
Face Matching
      ↓
Explainable Risk Engine
      ↓
Security Officer Review
```

SentinelID is designed as a **decision-support system**, not as a
replacement for a security officer.

------------------------------------------------------------------------

## 3. Key Capabilities

### Document Intelligence

Extracts structured fields such as:

-   Full name
-   Nationality
-   Date of birth
-   Date of issue when available from the visual document
-   Date of expiry
-   Issuing country code
-   Document number
-   Sex
-   Document type

Each field can retain its source:

``` text
OCR
MRZ
OCR + MRZ
```

### Real MRZ Analysis

The MRZ pipeline is:

``` text
MRZ Detection
→ Normalization
→ Format Detection
→ Field Parsing
→ Check-Digit Validation
→ OCR/MRZ Consistency
→ Final MRZ Status
```

The system separates **MRZ detected** from **MRZ validated** and exposes
raw MRZ, parsed fields, check-digit results, and overall status.

### Identity Verification

``` text
Camera
→ Face Detection
→ Liveness
→ Person Face
→ Document Face
→ Face Similarity
→ Identity Match
```

A missing liveness or face-match result is not silently treated as a
successful identity verification.

### Tamper Analysis

The prototype analyses document-image signals for potential visual
anomalies and uses the result as one input to the overall screening
process.

### Explainable Risk

The risk engine combines actual screening signals such as:

-   OCR
-   MRZ validation
-   OCR/MRZ consistency
-   Document validation
-   Expiry
-   Watchlist/blacklist result
-   Tamper analysis
-   Document face
-   Liveness
-   Face matching

The system does **not** use random risk values and does not use `0` as a
hidden placeholder for incomplete processing.

------------------------------------------------------------------------

## 4. Explainable Screening

Instead of returning only `PASS` or `FAIL`, SentinelID exposes
individual signals.

Example:

  Signal             Result
  ------------------ ---------
  OCR Extraction     PASS
  MRZ Validation     PASS
  Document Expiry    PASS
  Watchlist Check    PASS
  Tamper Detection   WARNING
  Document Face      PASS
  Liveness           PASS
  Face Match         PASS

The goal is to make the result traceable to evidence.

------------------------------------------------------------------------

## 5. MRZ and Identity Data Model

SentinelID keeps related fields separate:

``` text
Full Name
Nationality
Issuing Country
Date of Birth
Date of Issue
Date of Expiry
Document Number
Sex
Document Type
```

The system distinguishes nationality from issuing country.

Date of issue is not fabricated from a passport MRZ when it is not
present there; it is sourced from the visual/OCR document region when
available.

------------------------------------------------------------------------

## 6. Risk State Model

The risk engine explicitly represents processing state:

``` text
PENDING
CALCULATING
COMPLETED
FAILED
UNAVAILABLE
```

Example:

``` json
{
  "risk": {
    "status": "completed",
    "score": 42,
    "level": "medium",
    "reasons": []
  }
}
```

When required verification is incomplete:

``` json
{
  "risk": {
    "status": "pending",
    "score": null
  }
}
```

This prevents incomplete verification from being interpreted as a
low-risk result.

------------------------------------------------------------------------

## 7. Architecture

``` text
                    SENTINELID
                        │
              ┌─────────┴─────────┐
              │                   │
           Frontend             Backend
              │                   │
              │                FastAPI
              │                   │
              │       ┌───────────┼───────────┐
              │       │           │           │
              │      OCR          MRZ      Validation
              │       │           │           │
              │       └───────────┼───────────┘
              │                   │
              │              Tamper Analysis
              │                   │
              │            Document Face
              │                   │
              │              Liveness
              │                   │
              │             Face Matching
              │                   │
              │              Risk Engine
              │                   │
              └────────────── Database
```

------------------------------------------------------------------------

## 8. Technology Stack

### Frontend

-   React
-   TypeScript
-   Browser camera APIs
-   Responsive screening dashboard

### Backend

-   Python
-   FastAPI
-   REST APIs

### AI / Computer Vision

-   OCR
-   MRZ parsing and validation
-   Image preprocessing
-   Face detection
-   Liveness verification
-   Face similarity

### Data

-   SQLite for the hackathon prototype
-   Persistent screening records
-   Local simulated validation/watchlist data

The verification layer is structured so authorized external data sources
can be integrated later.

------------------------------------------------------------------------

## 9. Persistence and Auditability

Every screening receives a persistent ID.

``` text
Screening
→ Processing
→ Database
→ Screening Result
```

The result page loads the saved screening from the backend rather than
depending only on temporary frontend state.

This supports:

-   Screening History
-   Reopening previous screenings
-   Browser refresh
-   Persistent risk results
-   Traceable processing results

------------------------------------------------------------------------

## 10. Failure-Safe Design

SentinelID distinguishes:

``` text
PASS
FAIL
PENDING
UNAVAILABLE
```

Examples:

**Liveness not completed**

``` text
Identity Verification: PENDING
```

**MRZ parser failed**

``` text
MRZ: INVALID / UNAVAILABLE
```

**Risk calculation not completed**

``` text
Risk: PENDING
```

Missing evidence is never silently converted into a successful result.

------------------------------------------------------------------------

## 11. Performance Approach

The pipeline is modular so individual stages can be optimized
independently.

``` text
Document
   ↓
Preprocessing
   ├── OCR
   └── MRZ

Verification
   ├── Validation
   ├── Database
   └── Tamper

Identity
   ├── Document Face
   ├── Liveness
   └── Face Match

All required signals
   ↓
Risk Engine
```

Completed screening results are persisted so a browser refresh does not
require unnecessary recomputation.

------------------------------------------------------------------------

## 12. Prototype Scope

SentinelID is a **hackathon prototype**, not a production border-control
system.

The prototype demonstrates the complete workflow using:

-   Sample/mock documents
-   Local verification databases
-   Browser camera
-   AI-assisted document processing
-   Explainable risk calculation

It does not claim to connect to real government databases.

------------------------------------------------------------------------

## 13. Security & Privacy Principles

The prototype follows security-oriented design principles:

-   Validate uploaded files.
-   Avoid unnecessary exposure of identity images.
-   Avoid logging sensitive document data unnecessarily.
-   Protect API endpoints.
-   Sanitize OCR output.
-   Avoid unnecessary biometric retention.
-   Use authorized data sources for real deployments.
-   Keep a human in the decision loop.

------------------------------------------------------------------------

## 14. Testing

### Unit Testing

Test:

-   MRZ parser
-   Check-digit calculator
-   Name parser
-   Date parser
-   Validation rules
-   Risk calculation

### Integration Testing

``` text
Upload
→ OCR
→ MRZ
→ Validation
→ Risk
```

### Identity Testing

``` text
Camera
→ Face
→ Liveness
→ Face Match
```

### Persistence Testing

``` text
Create Screening
→ Save
→ GET Screening
→ Refresh
→ Result remains available
```

------------------------------------------------------------------------


## 15. Future Scope

### Advanced Prototype

-   More document formats
-   Improved OCR confidence handling
-   Better document-type classification
-   Stronger document-image analysis
-   Improved liveness
-   Better audit trails
-   Role-based access

### Deployment Architecture

Subject to authorization and applicable law:

``` text
SentinelID
   │
   ├── Authorized Identity Sources
   ├── Authorized Watchlists
   ├── Document Verification Services
   └── Secure Audit Infrastructure
```

------------------------------------------------------------------------

## 16. Why SentinelID

SentinelID focuses on the **complete verification workflow**, rather
than presenting OCR as the entire solution.

``` text
DOCUMENT
   +
OCR
   +
MRZ
   +
VALIDATION
   +
TAMPER ANALYSIS
   +
BIOMETRICS
   +
LIVENESS
   +
RISK EXPLANATION
```

The central engineering principle is:

> **Every important result should be backed by a measurable signal and a
> traceable processing step.**

------------------------------------------------------------------------

## 17. Running the Prototype

Use the commands defined by the repository. A typical development setup
is:

### Backend

``` bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

``` bash
cd frontend
npm install
npm run dev
```

------------------------------------------------------------------------

## 18. Hackathon Positioning

SentinelID demonstrates a practical AI-assisted security workflow by
connecting:

**Document Intelligence + MRZ Validation + Computer Vision +
Biometrics + Explainable Risk**

into one prototype.

The system is designed around three principles:

### Detect

Identify suspicious or inconsistent signals.

### Verify

Cross-check document, database, and biometric evidence.

### Explain

Show the officer which signals produced the result.

------------------------------------------------------------------------


