### 🚀 Offline RAG System

An end-to-end **Retrieval-Augmented Generation (RAG)** system for intelligent question answering over technical documents.

The system combines **document processing, vector retrieval, graph-based retrieval, local LLM inference, and source-grounded responses** in an offline-oriented architecture.

The project is divided into two major components:

- **Part A** — Document Processing & Knowledge Base Construction
- **Part B** — RAG Application & Interactive Question Answering

A research paper related to the project is also included in the repository under the `research/` directory.

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Project Structure](#-project-structure)
- [Part A - Document Processing](#-part-a---document-processing)
- [Part B - RAG Application](#-part-b---rag-application)
- [Technology Stack](#-technology-stack)
- [Requirements](#-requirements)
- [Clone the Repository](#-clone-the-repository)
- [Offline Environment Setup](#-offline-environment-setup)
- [Required Runtime Services](#-required-runtime-services)
- [Offline Resources](#-offline-resources)
- [Running Part B](#-running-part-b)
- [Application Verification](#-application-verification)
- [Knowledge Base Setup](#-knowledge-base-setup)
- [Database Restoration](#-database-restoration)
- [Troubleshooting](#-troubleshooting)
- [Research Paper](#-research-paper)
- [Large Files and GitHub](#-large-files-and-github)
- [Security](#-security)
- [End-to-End Workflow](#-end-to-end-workflow)
- [Future Improvements](#-future-improvements)
- [Author](#-author)

---

# 📖 Overview

This project implements an **offline-oriented Retrieval-Augmented Generation (RAG) system** for question answering over technical documents.

Instead of relying only on the knowledge stored inside a Large Language Model (LLM), the system retrieves relevant information from a document knowledge base and provides that information to the LLM as context for generating grounded responses.

The overall workflow is:

```text
Technical Documents
        │
        ▼
┌───────────────────────┐
│       Part A          │
│ Document Processing   │
└───────────┬───────────┘
            │
            ▼
   Text Extraction
            │
            ▼
     Chunking / Metadata
            │
       ┌────┴────┐
       ▼         ▼
   Qdrant      Neo4j
   Vectors     Graph
       │         │
       └────┬────┘
            │
            ▼
┌───────────────────────┐
│       Part B          │
│   Retrieval Pipeline  │
└───────────┬───────────┘
            │
            ▼
      Relevant Context
            │
            ▼
     Local LLM / Ollama
            │
            ▼
    Grounded Answer
            │
            ▼
     Sources / Pages
```

---

# ✨ Key Features

### 📄 Document Processing

- PDF-based document processing
- Text extraction
- Document chunking
- Metadata generation
- Proposition generation
- Knowledge graph preparation
- Vector database ingestion
- Graph database ingestion

### 🔎 Retrieval

The system uses multiple retrieval components:

- **Qdrant** for vector-based retrieval
- **Neo4j** for graph-based retrieval
- **MongoDB** for application and library data
- Retrieval pipeline for obtaining relevant context

### 🤖 Local LLM

The application supports local LLM inference through **Ollama**, allowing the system to generate responses using a locally hosted model.

### 💬 Interactive Question Answering

Part B provides an application interface for:

- User authentication
- Library/document selection
- Question answering
- Chat functionality
- Source display
- Page-level source references

### 📴 Offline-Oriented Architecture

The project supports deployment using:

- Local Python environment
- Offline model resources
- Local databases
- Local documents
- Local LLM inference

This makes the architecture suitable for environments where documents or data should remain within the local infrastructure.

---

# 🏗 System Architecture

```text
                       ┌─────────────────────┐
                       │   Technical PDFs    │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │       PART A        │
                       │ Document Processing │
                       └──────────┬──────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
                 ▼                ▼                ▼
          ┌────────────┐   ┌────────────┐   ┌────────────┐
          │   Qdrant   │   │   Neo4j    │   │  MongoDB   │
          │   Vector   │   │   Graph    │   │ Application│
          │    DB      │   │    DB      │   │    Data    │
          └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
                │                │                │
                └────────────────┼────────────────┘
                                 │
                                 ▼
                       ┌─────────────────────┐
                       │       PART B        │
                       │ Retrieval Pipeline  │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │    Local LLM        │
                       │      Ollama         │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │ Answer + Sources    │
                       └─────────────────────┘
```

---

# 📁 Project Structure

```text
RAG/
│
├── .gitignore
├── README.md
│
├── research/
│   └── KRUTRIM RAG.docx
│
├── parta/
│   ├── document/
│   │   ├── command.txt
│   │   └── Untitled
│   │
│   ├── extraction/
│   │   ├── extraction_server.py
│   │   └── master.py
│   │
│   ├── frontend/
│   │   ├── index.html
│   │   └── isro-logo.png
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── build_metadata.py
│   │   ├── chunk.py
│   │   ├── ingest_neo4j.py
│   │   ├── ingest_qdrant.py
│   │   ├── propositions.py
│   │   └── triple_rep.py
│   │
│   ├── main_api.py
│   ├── pipeline_controller.py
│   ├── test.py
│   └── text_worker.py
│
├── partb/
│   ├── frontend/
│   │
│   ├── llm/
│   │   └── stream_client.py
│   │
│   ├── retrieval/
│   │   ├── pipeline.py
│   │   └── prompt.py
│   │
│   ├── routers/
│   │   ├── auth_router.py
│   │   ├── chats_router.py
│   │   ├── meta_router.py
│   │   └── pdf_router.py
│   │
│   ├── services/
│   │   ├── messages.py
│   │   └── pages.py
│   │
│   ├── static/
│   ├── app.py
│   ├── auth_jwt.py
│   ├── config.py
│   └── db.py
│
└── supporting files
```

> **Note:** Large runtime resources, offline packages, models, raw documents, generated data, and deployment artifacts are intentionally excluded from the Git repository.

---

# 🧩 Part A — Document Processing

Part A is responsible for preparing documents and constructing the knowledge required by the RAG application.

### Main responsibilities

1. Document processing
2. Text extraction
3. Chunk creation
4. Metadata generation
5. Proposition generation
6. Knowledge graph preparation
7. Qdrant ingestion
8. Neo4j ingestion

### Main processing modules

```text
parta/processing/
│
├── build_metadata.py
├── chunk.py
├── ingest_neo4j.py
├── ingest_qdrant.py
├── propositions.py
└── triple_rep.py
```

### Part A Data

Runtime data is organized under:

```text
parta/data/
├── raw/
├── metadata/
├── processed/
├── checkpoints/
├── qdrant/
└── neo4j/
```

These directories contain document and processing data and are not stored in GitHub.

---

# 💬 Part B — RAG Application

Part B provides the application layer for interacting with the knowledge base.

### Main components

```text
partb/
│
├── app.py
├── auth_jwt.py
├── config.py
├── db.py
│
├── llm/
├── retrieval/
├── routers/
├── services/
├── frontend/
└── static/
```

### Part B responsibilities

- Authentication
- Library/document access
- Chat management
- Retrieval
- LLM communication
- Source handling
- Page information
- User-facing interface

The basic workflow is:

```text
User
 ↓
Login
 ↓
Select Library
 ↓
Ask Question
 ↓
Retrieval Pipeline
 ↓
Relevant Context
 ↓
Local LLM
 ↓
Generated Answer
 ↓
Sources / Page References
```

---

# 🛠 Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Backend | FastAPI |
| Application Server | Uvicorn |
| Vector Database | Qdrant |
| Graph Database | Neo4j |
| Application Database | MongoDB |
| Local LLM | Ollama |
| NLP | NLTK |
| ML / Embeddings | PyTorch / Sentence Transformers |
| Entity Processing | GLiNER |
| Frontend | HTML / JavaScript |
| Environment | Conda / Python |
| Deployment | Offline / Local |

---

# 📋 Requirements

The complete offline deployment requires:

- Windows environment
- Packed Python/Conda environment
- Part A source code/resources
- Part B source code
- Required offline models/resources
- MongoDB
- Qdrant
- Neo4j
- Ollama
- Required Ollama model
- Ingested knowledge-base data

---

# 📥 Clone the Repository

Clone the repository:

```bash
git clone https://github.com/siri-orog/RAG.git
```

Move into the project:

```bash
cd RAG
```

---

# 📴 Offline Environment Setup

The project can be deployed using a pre-packed Python environment.

The expected offline environment archive is:

```text
D:\offline_bundle\partb.tar.gz
```

The RAG project is expected at:

```text
D:\RAG\
├── parta\
└── partb\
```

---

## Step 1 — Copy Required Resources

The offline deployment requires the following resources:

```text
D:\offline_bundle\partb.tar.gz

D:\RAG\partb\

D:\RAG\parta\portable\

D:\RAG\parta\portable\nltk_data\

D:\RAG\parta\data\raw\

D:\RAG\parta\data\metadata\

D:\RAG\parta\data\checkpoints\
```

Database backups may also be transferred when available.

---

# 🐍 Extract the Python Environment

Create the environment directory:

```powershell
mkdir C:\envs\partb
```

Move into it:

```powershell
cd C:\envs\partb
```

Extract the packed environment:

```powershell
tar -xf D:\offline_bundle\partb.tar.gz
```

Run:

```powershell
.\Scripts\conda-unpack.exe
```

Verify Python:

```powershell
C:\envs\partb\python.exe --version
```

Expected version:

```text
Python 3.10.9
```

---

# 🗄 Required Runtime Services

Part B depends on the following local services:

| Service | Port | Purpose |
|---|---:|---|
| MongoDB | 27017 | Users, chats and library data |
| Qdrant | 6333 | Vector search |
| Neo4j | 7687 | Graph retrieval |
| Ollama | 11434 | Local LLM inference |

All required services should be running before using the complete RAG workflow.

---

# 🟢 MongoDB

MongoDB stores application-related data including:

- Users
- Chats
- Library information

Default port:

```text
27017
```

---

# 🔵 Qdrant

Qdrant is used for vector-based retrieval.

Default port:

```text
6333
```

The required document vectors must already be ingested for retrieval to return results.

---

# 🟣 Neo4j

Neo4j is used for graph-based retrieval.

Default port:

```text
7687
```

The required knowledge graph data must be available for graph retrieval.

---

# 🟠 Ollama

Ollama provides local LLM inference.

Default port:

```text
11434
```

The model configured in:

```text
partb/config.py
```

should be available in Ollama.

The configuration uses:

```text
OLLAMA_MODEL
```

to identify the required model.

---

# 📦 Offline Resources

Offline model and supporting resources are stored outside GitHub.

Expected location:

```text
parta/portable/
```

This may contain resources such as:

```text
parta/portable/
├── docling/
├── gliner/
├── gliner_cache/
├── nltk_data/
├── nomic/
└── reranker/
```

These resources can be large and are therefore excluded from the repository.

---

# 🔤 NLTK Data

If the NLTK resources are not detected correctly, ensure the expected directory exists:

```text
D:\RAG\parta\portable\nltk_data
```

If required, copy the provided NLTK resources:

```powershell
Copy-Item -Recurse D:\RAG\parta\portable\nlkt_data D:\RAG\parta\portable\nltk_data
```

---

# ▶️ Running Part B

Once the Python environment and required services are ready:

### 1. Open PowerShell

```powershell
cd D:\RAG
```

### 2. Set Python Path

```powershell
$env:PYTHONPATH = "D:\RAG"
```

### 3. Start the FastAPI Application

```powershell
C:\envs\partb\python.exe -m uvicorn partb.app:app --host 0.0.0.0 --port 9000
```

The application will be available at:

```text
http://localhost:9000
```

Open the address in a browser.

---

# 🧪 Application Import Test

Before starting the application, the Part B module can be tested with:

```powershell
cd D:\RAG
```

```powershell
$env:PYTHONPATH = "D:\RAG"
```

Then:

```powershell
C:\envs\partb\python.exe -c "from partb.app import app; print('app OK')"
```

Expected output:

```text
app OK
```

---

# ✅ Application Verification

After starting the application:

### 1. Login

Open:

```text
http://localhost:9000
```

and log in.

### 2. Check Application Health

Verify that the required backend services are available.

### 3. Open the Library

Select an available document/library.

Example:

```text
GSAT
```

### 4. Ask a Question

Example:

```text
When was Bhaskara-1 launched?
```

### 5. Check the Answer

The application should retrieve relevant information and provide a generated answer.

### 6. Check Sources

Use the source information associated with the answer to inspect the referenced document/page.

---

# 🧠 Knowledge Base Setup

Part B requires an already prepared knowledge base.

There are two approaches.

## Option 1 — Restore Existing Data

Restore the existing:

- MongoDB data
- Qdrant data
- Neo4j data

This allows the application to use an already constructed knowledge base.

## Option 2 — Process Documents Using Part A

Part A can be used when:

- New PDFs need to be processed
- The knowledge base needs to be rebuilt
- Documents need to be re-ingested

The processed information is then made available to the retrieval layer.

> Part A does not need to remain continuously running for normal Part B chat when the required knowledge-base data is already available.

---

# 💾 Database Restoration

If MongoDB backup data is available, it can be restored.

Example:

```powershell
mongodump --db rag_system --out E:\RAG\offline_bundle\mongo_dump
```

Restore:

```powershell
mongorestore --db rag_system D:\offline_bundle\mongo_dump\rag_system
```

Qdrant and Neo4j can similarly be restored from their available backup/snapshot data.

If the databases are empty, the required Part A ingestion workflow must be used to build the knowledge base.

---

# 🔐 Security

Do not commit sensitive information to GitHub.

Never upload:

- Passwords
- Authentication secrets
- Private keys
- Database credentials
- Private connection strings
- API keys
- Production secrets

Use local configuration for deployment-specific credentials.

---

# 🐛 Troubleshooting

## `conda-unpack.exe` not found

Make sure the environment archive was extracted completely.

Check:

```text
C:\envs\partb\Scripts\
```

for:

```text
conda-unpack.exe
```

---

## `ModuleNotFoundError: No module named 'partb'`

Run:

```powershell
cd D:\RAG
$env:PYTHONPATH = "D:\RAG"
```

Then start the application again.

---

## Health Status Is Degraded

Check whether the following services are running:

```text
MongoDB
Qdrant
Neo4j
Ollama
```

Also verify that the configured ports are correct.

---

## No Documents / Books Appear

If the library is empty:

- MongoDB may not contain the required library data.
- Restore the MongoDB backup.
- Or rebuild the knowledge base using the Part A workflow.

---

## No Answers or Sources

Possible causes:

- Qdrant is empty
- Neo4j is empty
- Required knowledge base was not ingested
- Incorrect document/library identifier
- Required service is unavailable

Verify that the selected library exists and that the retrieval databases contain the required data.

---

## Page Preview Is Blank

Verify that the required raw PDF exists in:

```text
parta/data/raw/
```

Also verify that the NLTK resources are available at:

```text
parta/portable/nltk_data/
```

---

# 📄 Research Paper

A research paper related to this project is included in the repository.

The paper is available under:

```text
research/
└── KRUTRIM RAG.docx
```

### Research Focus

The research work is associated with the development and study of the RAG architecture implemented in this project.

The repository therefore contains both:

- The implementation
- The corresponding research documentation

### Research Paper

📄 **[Open KRUTRIM RAG Research Paper](research/KRUTRIM%20RAG.docx)**

> For academic publication, the research paper should be submitted separately to an appropriate conference, journal, or preprint platform. GitHub serves as the project repository and research artifact.

---

# 🚫 Large Files and GitHub

This project uses several large offline/runtime resources that are intentionally excluded from GitHub.

Examples include:

```text
modules/
parta/modules/
parta/data/
parta/portable/
partb/deploy/
```

These directories may contain:

- Offline Python packages
- Large machine-learning libraries
- Raw PDFs
- Model resources
- Generated processing data
- Vector database data
- Graph database data
- Deployment artifacts

Keeping these files outside GitHub keeps the repository manageable while allowing the complete offline deployment bundle to be maintained separately.

---

# 🧹 Git Ignore

The repository uses `.gitignore` rules for large and generated resources.

Important exclusions include:

```gitignore
/modules/
/parta/modules/

/parta/data/

/parta/portable/

/partb/deploy/

__pycache__/
*.py[cod]
```

---

# 🔄 End-to-End Workflow

```text
                 TECHNICAL DOCUMENTS
                         │
                         ▼
                 ┌───────────────┐
                 │    PART A     │
                 │  Processing   │
                 └───────┬───────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          Metadata     Qdrant      Neo4j
             │         Vectors      Graph
             │           │           │
             └───────────┼───────────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    PART B     │
                 │  RAG System   │
                 └───────┬───────┘
                         │
                         ▼
                    User Query
                         │
                         ▼
                 Retrieval Pipeline
                         │
                         ▼
                  Relevant Context
                         │
                         ▼
                    Local LLM
                      Ollama
                         │
                         ▼
                  Generated Answer
                         │
                         ▼
                   Source / Page
```

---

# 📊 Part A vs Part B

| Capability | Part A | Part B |
|---|:---:|:---:|
| PDF Processing | ✅ | ❌ |
| Text Extraction | ✅ | ❌ |
| Chunking | ✅ | ❌ |
| Metadata Generation | ✅ | ❌ |
| Proposition Generation | ✅ | ❌ |
| Qdrant Ingestion | ✅ | ❌ |
| Neo4j Ingestion | ✅ | ❌ |
| Authentication | ❌ | ✅ |
| Chat Interface | ❌ | ✅ |
| Retrieval Pipeline | Supporting | ✅ |
| Local LLM Integration | Supporting | ✅ |
| Source Handling | Supporting | ✅ |
| Interactive Q&A | ❌ | ✅ |

---

# 🎯 Potential Applications

The architecture can be useful for:

- Technical document question answering
- Scientific document exploration
- Engineering knowledge systems
- Internal knowledge assistants
- Offline AI assistants
- Private document search
- Research document analysis
- Document-grounded conversational AI

---

# 🚀 Future Improvements

Potential future improvements include:

- Improved hybrid retrieval
- Advanced reranking
- Better vector + graph retrieval fusion
- Multi-document reasoning
- Improved citation generation
- Retrieval evaluation
- Automated knowledge-base updates
- Advanced access control
- Performance monitoring
- Containerized deployment
- Automated offline deployment

---

# ⭐ Project

If you find this project useful, consider starring the repository.

**Repository:**

https://github.com/siri-orog/RAG

---

# 👩‍💻 Author

**Siri Lasya Reddy**

GitHub:

https://github.com/siri-orog


and make the **PDF the primary link** in README.

Also, don't claim the paper is *published* just because it's on GitHub. GitHub can host the paper, while actual journal/conference publication is a separate step.
