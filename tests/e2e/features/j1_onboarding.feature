@J1 @US-BOR-001 @US-MTG-001
Feature: J1 Borrower to mortgage onboarding
  An underwriter registers a borrower, creates a mortgage with a pending loan and approves it. The approval moves the
  mortgage to ACTIVE, and servicing-service learns about the new mortgage from the MortgageCreated and LoanApproved
  events (mortgage-service -> SNS -> SQS -> servicing-service).

  Scenario: Underwriter onboards a new borrower and approves the mortgage
    Given I am logged in as "underwriter@capstone.local"
    When I register a new borrower
    Then the response status should be 201
    And the new borrower can be retrieved by its business ID
    When I create a mortgage of 320000.00 for the new borrower with a pending loan
    Then the response status should be 201
    And the mortgage status should be "PENDING"
    When I record the underwriting decision "APPROVED" for the new mortgage
    Then the response status should be 200
    And the mortgage status should be "ACTIVE"
    And the servicing history eventually shows "MORTGAGE_CREATED" and "LOAN_APPROVED"

  Scenario: A borrower ID that already exists is rejected
    Given I am logged in as "underwriter@capstone.local"
    When I register a borrower with the existing ID "BOR-001"
    Then the response status should be 409
    And the error code should be "BORROWER_ALREADY_EXISTS"
