# US-101: Send money to another customer

**As a** retail banking customer
**I want** to send money from my current account to another customer's account
**so that** I can pay people without visiting a branch.

## Acceptance criteria

1. A single transfer must be at least 1.00 EUR and at most 10,000.00 EUR.
2. The total of a customer's transfers in one calendar day must not exceed 25,000.00 EUR; a transfer that would take the total over this is rejected with the message "Daily transfer limit of 25,000.00 EUR reached".
3. Transfers above 2,000.00 EUR require a one-time passcode (OTP) before they are sent.
4. A fee of 0.5% of the amount is charged, with a minimum fee of 0.50 EUR.
5. A transfer larger than the available balance (amount plus fee) is rejected with the message "Insufficient funds".
6. An IBAN that fails the checksum is rejected with the message "Check the IBAN and try again" before the amount screen opens.
7. After a successful transfer the sender sees a confirmation with a reference number, and the transfer appears at the top of the transaction history.

## Notes

- Calendar day means 00:00 to 23:59 in the customer's time zone.
- Out of scope: scheduled and recurring transfers.
