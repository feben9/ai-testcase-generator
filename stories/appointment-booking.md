# US-105: Book a clinic appointment online

**As a** patient
**I want** to book and cancel clinic appointments online
**so that** I don't have to phone the clinic during opening hours.

## Acceptance criteria

1. An appointment can be booked at least 2 hours and at most 60 days before the slot starts.
2. Only slots marked "Available" in the clinic calendar can be selected; booked slots are shown greyed out.
3. A patient cannot hold two appointments that overlap in time; the second booking is rejected with the message "You already have an appointment at this time".
4. A patient can cancel an appointment up to 24 hours before it starts; later cancellations are rejected with the message "Appointments can only be cancelled up to 24 hours in advance".
5. After booking, the patient receives a confirmation email with the date, time and clinic address.
6. The calendar should load quickly, even on slow connections.

## Notes

- Slots are 30 minutes long.
