@J4 @US-SEC-001 @US-SEC-002
Feature: J4 Unauthorized users are denied
  Every protected route needs a valid JWT (401 otherwise) and one of the roles allowed for that route (403
  ACCESS_DENIED otherwise). The role matrix is in docs/security/security-controls.md (RBAC matrix); the API contracts list x-roles.

  Scenario: Support user cannot approve a loan
    Given I am logged in as "support@capstone.local"
    When I record the underwriting decision "APPROVED" for mortgage "MTG-1001"
    Then the response status should be 403
    And the error code should be "ACCESS_DENIED"
    And mortgage "MTG-1001" should still be "ACTIVE"

  Scenario Outline: <user> cannot <action>
    Given I am logged in as "<user>"
    When I try to <action>
    Then the response status should be 403
    And the error code should be "ACCESS_DENIED"

    Examples:
      | user                       | action                          |
      | servicing@capstone.local   | register a borrower             |
      | risk@capstone.local        | post a payment to MTG-1001      |
      | underwriter@capstone.local | run the delinquency evaluation  |
      | support@capstone.local     | read the borrower BOR-001       |

  Scenario Outline: A request with <credentials> is rejected with 401
    When I read the borrower "BOR-001" with <credentials>
    Then the response status should be 401
    And the error code should be "<code>"

    Examples:
      | credentials      | code          |
      | no token         | UNAUTHORIZED  |
      | a tampered token | INVALID_TOKEN |

  Scenario: The assistant also requires a token
    When I ask the assistant "What happens when a payment is 30 days late?" without a token
    Then the response status should be 401
