# Design references

Primary technical documentation consulted on 2026-10-16. These references support design choices; they are not verification of this project's deployed behavior.

1. pgvector documentation: exact vector search, hybrid-search examples and filtered ANN behavior. https://github.com/pgvector/pgvector
2. PostgreSQL row security: policies, owner behavior and FORCE ROW LEVEL SECURITY. https://www.postgresql.org/docs/current/ddl-rowsecurity.html
3. PostgreSQL text search: tsvector, query parsing and ranking. https://www.postgresql.org/docs/current/textsearch-controls.html
4. PostgreSQL query parsing functions. https://www.postgresql.org/docs/current/functions-textsearch.html
5. OpenAI vector embeddings guide: real embedding requests and vector dimensions. https://developers.openai.com/api/docs/guides/embeddings
6. OpenAI embeddings API contract. https://developers.openai.com/api/reference/resources/embeddings/methods/create

Implementation choice: combine lexical and dense rankings using RRF, use a single transactional store and favor an exact authorized-subset baseline until measurements justify an ANN redesign.
