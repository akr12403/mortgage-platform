// J5: grounded Q&A. The answer's citations must point at real knowledge-base chunks
// (ai/mortgage-knowledge-assistant/knowledge/<version>/<document>.md -> chunk id "<document>:<version>:c-NN").
import { Given, Then, When } from "@cucumber/cucumber";
import assert from "node:assert/strict";
import { similarityThreshold } from "../support/config.mjs";

const CHUNK_ID = /^([a-z0-9-]+):v\d+:c-\d+$/;

Given("the knowledge assistant is ready", async function () {
  const response = await this.assistant.ready();
  assert.equal(response.status, 200,
    "knowledge-assistant is not ready (GET /health/ready). It needs the database, an ingested knowledge base " +
    "(docker compose run --rm knowledge-ingest) and an AI provider (LLM_API_KEY in your .env). " +
    `Checks: ${JSON.stringify(response.body)}`);
});

When("I ask the assistant {string}", async function (question) {
  this.last = await this.assistant.ask(await this.token(), question);
});

When("I ask the assistant {string} without a token", async function (question) {
  this.last = await this.assistant.ask(undefined, question);
});

Then("the answer should not be empty", function () {
  assert.ok(typeof this.last.body.answer === "string" && this.last.body.answer.trim(), this.describe());
});

Then("the answer should cite at least one passage of the knowledge base", function () {
  const { citations, confidence } = this.last.body;
  assert.ok(Array.isArray(citations) && citations.length > 0, `no citations: ${this.describe()}`);
  assert.ok(confidence >= similarityThreshold, `confidence ${confidence} below ${similarityThreshold}`);
});

Then("every citation should name its document, section and chunk", function () {
  for (const citation of this.last.body.citations) {
    assert.ok(citation.documentId && citation.section && citation.chunkId, JSON.stringify(citation));
    const match = CHUNK_ID.exec(citation.chunkId);
    assert.ok(match, `chunk id "${citation.chunkId}" is not <document>:<version>:c-NN`);
    assert.equal(`${match[1]}.md`, citation.documentId, `chunk ${citation.chunkId} cited for ${citation.documentId}`);
  }
});

Then("the answer should have no citations", function () {
  assert.deepEqual(this.last.body.citations, [], this.describe());
});

Then("the confidence should be below the similarity threshold", function () {
  assert.ok(this.last.body.confidence < similarityThreshold,
    `confidence ${this.last.body.confidence} is not below ${similarityThreshold}: ${this.describe()}`);
});
