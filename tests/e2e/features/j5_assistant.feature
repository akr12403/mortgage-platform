@J5 @US-AI-001 @assistant
Feature: J5 Grounded answer from the knowledge assistant
  The assistant answers policy questions only from retrieved passages of the approved knowledge base and returns
  citations to those passages. A question the knowledge base can't answer gets "insufficient context" and no
  citations, instead of an invented answer. In the pipeline the model is a stub and the embedder is offline (the
  assistant's own code runs unchanged); locally the journey runs against your real LLM.

  Background:
    Given the knowledge assistant is ready
    And I am logged in as "servicing@capstone.local"

  Scenario: A policy question gets a grounded answer with citations
    When I ask the assistant "What happens when a mortgage payment is 30 days past due?"
    Then the response status should be 200
    And the answer should not be empty
    And the answer should cite at least one passage of the knowledge base
    And every citation should name its document, section and chunk

  Scenario: A question outside the knowledge base gets no invented answer
    When I ask the assistant "Who won the football world cup in 1998?"
    Then the response status should be 200
    And the answer should have no citations
    And the confidence should be below the similarity threshold
