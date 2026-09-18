We are replacing the Hermes Agent orchestrator with a highly maintainable, 100% local, multi-user and multi-channel agentic solution based on LangGraph, packaged inside a Linux Docker container. We want to move away from managing ALLOWED_USERS via static .env strings and instead leverage a proper Database + API architecture for advanced user management, permissions, and administration.

CRITICAL WORKSPACE & MEMORY INSTRUCTIONS FOR CLAUDE:
1. Current Directory: You are running directly inside the target directory: "/Users/mac/Documents/Code/ChannelAgent". All new implementation files, Dockerfiles, and scripts must be built here.
2. Source Directory for Audit: The legacy project is located at the absolute path: "/Users/mac/Documents/Code/Hermes". You will need to read files from that external directory during the discovery phase.
3. Git Repository Initialization: If not already done, initialize a clean, independent Git repository here in ChannelAgent ('git init') and establish proper '.gitignore' files protecting secrets and '.env' files.
4. Claude Memory Management: 
   - Read and respect any existing global memory or system prompts configured for this workspace.
   - Actively maintain and update your local context memory by creating/updating a '.claudecode.md' project-memory file inside this ChannelAgent directory so future sessions retain today's architectural decisions.

Database Security & Encryption Requirements:
- Application-Layer Encryption: All critical and sensitive user data stored in the database (such as raw email addresses, Matrix tokens, access keys, or personal metadata) MUST be encrypted at rest using symmetric encryption (e.g., cryptography's Fernet / AES-256).
- Encryption Key Management: The encryption key must be loaded dynamically from the local '.env' file and must never be committed to Git or stored inside the database itself.
- Implement clear helper functions in the database layer to automatically encrypt data before database writes and decrypt data upon database reads.

Legacy Repository Technical Context (to read from /Users/mac/Documents/Code/Hermes):
- Local LLM Gateway: A native llama-server binary is executed on macOS at: `/Users/mac/Documents/Code/Hermes/macos-arm64/vendor/llama.cpp-prebuilt/current/llama-server`. It serves 'Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf' on port 8080 (context 65536).
- Legacy API & Dashboard Context: The '.env' file in the Hermes directory exposes 'API_SERVER_PORT=8645', 'API_SERVER_ENABLED=true', and 'HERMES_DASHBOARD=1'. 

Mandatory Project Conventions:
- Language Rule: All code comments, scripts, Dockerfiles, and documentation MUST be written in English only.
- Documentation updates: Any architectural change we make must be documented immediately by updating 'docs/ARCHITECTURE.md' inside this folder (including updated Mermaid diagrams reflecting the multi-channel data flow, encrypted database layer, and routing). Keep a factual, technical prose style.

Your step-by-step roadmap for this session:

Step 1: Remote Repository Audit & Discovery
- Scan the external "/Users/mac/Documents/Code/Hermes" directory to locate any existing database initialization scripts, schemas, or migrations (look for .db, .sqlite, SQL files, Prisma or SQLAlchemy schemas).
- Locate the legacy API server implementation running on port 8645 in that folder to analyze how it routed requests.
- Verify if there are existing tables or endpoints for users, admins, or channels that we can extract, copy over, or reuse here in ChannelAgent. Summarize your findings in English.

Step 2: Porting & Custom Architecture Implementation (Inside ChannelAgent)
- Copy or port over the relevant database configuration and building blocks found during the Hermes audit, adapting them to include the database encryption layer.
- Design a dynamic authentication layer querying the secure DB/API to validate incoming user requests.
- Normalized Event Schema: Handle incoming messages from Telegram, incoming Emails, and Matrix/Element. Normalize them into a standard event schema containing (user_id, channel, message_text).
- State & Isolation: Use LangGraph's native Checkpointer mechanism with distinct 'thread_id' values (e.g., 'telegram_{user_id}', 'email_{email_hash}', or 'matrix_{user_id}') to isolate user conversation states.
- File Structure: Code the containerized Python layout (config validation, encryption utils, channel adapters, and 'graph.py' for the LangGraph workflow). Ensure the Linux Docker container can safely reach the Mac host's 'llama-server' on port 8080 during local development.

Please begin by running Step 1 (the remote audit of the Hermes directory), explain what database/API blocks are available to port over, and initialize the Git repository, encryption hooks placeholder, and '.claudecode.md' file in the current directory.
