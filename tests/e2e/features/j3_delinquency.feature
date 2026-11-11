@J3 @US-DEL-001
Feature: J3 Missed payment leads to delinquency
  A failed installment that is 30 or more days past due makes an ACTIVE mortgage DELINQUENT. mortgage-service
  publishes PaymentMissed and LoanDelinquent; servicing-service builds the delinquency snapshot from them.
  Severity bands: 30-59 days MODERATE, 60-89 SEVERE, 90+ CRITICAL.

  Scenario: The seeded delinquent mortgage MTG-1002 reports its delinquency
    Given I am logged in as "risk@capstone.local"
    When I request the delinquency status of mortgage "MTG-1002"
    Then the response status should be 200
    And the delinquency status should be "DELINQUENT" with at least 30 days past due and a severity

  Scenario: An installment missed 45 days ago makes an active mortgage delinquent
    Given an active mortgage created for this scenario
    And I am logged in as "servicing@capstone.local"
    When I post a "FAILED" payment of 1650.00 due 45 days ago
    Then the response status should be 200
    And the mortgage status should be "DELINQUENT"
    And the delinquency status eventually shows "DELINQUENT" with severity "MODERATE"
    And the servicing history eventually shows "PAYMENT_MISSED" and "DELINQUENCY_ASSIGNED"
