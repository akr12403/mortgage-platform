@J2 @US-PAY-001 @US-SRV-001
Feature: J2 Mortgage payment visible in the servicing history
  A servicing agent posts a payment. mortgage-service lowers the outstanding balance and publishes PaymentReceived;
  servicing-service records it in the mortgage's servicing history. Payments are idempotent per Idempotency-Key.

  Background:
    Given an active mortgage created for this scenario
    And I am logged in as "servicing@capstone.local"

  Scenario: Servicing agent posts a payment and sees it in the servicing history
    When I post a "POSTED" payment of 1850.00 due 2 days ago
    Then the response status should be 200
    And the outstanding balance should have gone down by 1850.00
    And the payment should be listed for the mortgage
    And the servicing history eventually shows "PAYMENT_POSTED"

  Scenario: Sending the same payment twice with one Idempotency-Key posts it once
    When I post a "POSTED" payment of 500.00 due 2 days ago
    And I send the same payment again with the same Idempotency-Key
    Then the response status should be 200
    And the response header "Idempotent-Replayed" should be "true"
    And the outstanding balance should have gone down by 500.00
    And the servicing history eventually shows "PAYMENT_POSTED" exactly once
