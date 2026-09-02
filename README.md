MGR Logistics
Delivery Assignment Intelligence System

MGR Logistics is a Python-based logistics management system that helps process delivery requests, validate addresses, calculate route distances, and identify deliveries that are ready for assignment.

The project includes two graphical interfaces:

User Delivery Portal — customers or users can submit delivery requests.
Admin Dashboard — administrators can process and analyse the delivery queue.
Features
User Delivery Portal

Users can enter delivery information through a simple graphical form.

The portal collects:

Customer Name
Pickup Address
Drop-off Address
Package Weight
Special Instructions

Each delivery request is automatically assigned a unique Job ID and saved to the delivery queue.

Admin Dashboard

The admin dashboard processes the delivery queue and displays:

Total Records
Total Jobs
Assignable Jobs
Flagged Jobs
Pickup Status
Drop-off Status
Route Distance
Assignment Status
Flag Reasons
Detailed Job Information
How the System Works
USER
  │
  ▼
USER DELIVERY PORTAL
  │
  ▼
DELIVERY QUEUE (CSV)
  │
  ▼
LOGISTICS AGENT
  │
  ├── Normalizes Delivery Records
  │
  ├── Resolves Pickup Address
  │
  ├── Resolves Drop-off Address
  │
  ├── Calculates Route Distance
  │
  ├── Validates Delivery Information
  │
  └── Classifies Jobs
  │
  ▼
ADMIN DASHBOARD
Job Classification

A delivery job is marked as Assignable when:

The pickup address is successfully resolved.
The drop-off address is successfully resolved.
Both locations have usable coordinates.

A delivery job is Flagged when:

The pickup address is missing.
The drop-off address is missing.
An address cannot be resolved.
Address information is invalid or incomplete.

The system does not create or guess coordinates for invalid addresses.

Project Structure
MGR Logistics/
│
├── logistics_agent.py
│   Main logistics processing and analysis pipeline
│
├── gui.py
│   Admin dashboard for analysing delivery jobs
│
├── user_portal.py
│   User interface for submitting delivery requests
│
├── demo_run.py
│   Demonstrates the logistics pipeline
│
├── delivery_queue.csv
│   Delivery request queue
│
├── sample_delivery_queue.csv
│   Sample delivery data for testing
│
├── test_assignable_jobs.py
│   Tests job creation and assignment logic
│
├── test_duplicate_id_fix.py
│   Tests duplicate and malformed IDs
│
├── test_empty_sources.py
│   Tests empty and invalid input sources
│
├── test_reusable_cache.py
│   Tests reusable resolver and distance caches
│
├── README.md
│   Project documentation
│
└── .gitignore
Technologies Used
Python
Tkinter
CSV
JSON
Python Dataclasses
Haversine Distance Calculation

The project does not require external Python packages.
