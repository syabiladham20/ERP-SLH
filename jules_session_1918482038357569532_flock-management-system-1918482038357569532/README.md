# Farm Manager - Poultry Flock Management System

A Flask-based web application for managing poultry flocks, tracking daily performance metrics, and visualizing data.

## Features

*   **Flock Management:** Create, Close, and Switch Phase (Rearing/Production) for flocks. Support for manual House naming.
*   **Daily Data Entry:** Mobile-friendly form for recording:
    *   Mortality & Culls (Male/Female)
    *   Feed Intake (Grams per Bird - Male/Female)
    *   Water Consumption (Meter Readings -> Calculated 24h Intake)
    *   Body Weight & Uniformity (Male/Female)
    *   Egg Production & Defects
    *   Lighting & Feed Cleanup Times
    *   Clinical Notes & Photo Uploads
*   **Data Import:** Bulk import historical data from Excel files (multi-sheet support).
*   **Visualization:** Interactive charts for Egg Production, Mortality, and Body Weight.
*   **Weekly Summaries:** Aggregated performance data per week.

## Installation

1.  **Clone the repository.**
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Initialization

Before running the application for the first time, initialize the database:

```bash
python init_db.py
```
This creates `instance/farm.db` and populates initial House names.

## Configuration

For production environments, you should set a secure secret key.

1.  **Generate a secret key:**
    ```bash
    python generate_key.py
    ```
    Copy the generated key.

2.  **Create a `.env` file:**
    Create a file named `.env` in the root directory and add the following line:
    ```
    SECRET_KEY=your_generated_key_here
    ```

## Running the Application

```bash
flask run
```
Access the application at `http://127.0.0.1:5000`.

## Usage Guide

### 1. Dashboard
The home page displays all **Active Flocks**.
*   **Batch ID:** {House}_{YYMMDD}_Batch{N}
*   **Phase:** Indicates if the flock is in Rearing or Production.
*   **Actions:**
    *   **Start Prod / Revert Rearing:** Toggle the flock phase.
    *   **History:** View detailed logs and charts.
    *   **Close:** Mark the flock as Inactive (End Cycle).

### 2. Manage Flocks (Create New)
Go to **Manage Flocks** to create a new flock.
*   **House Name:** Select an existing house or **type a new name** to create a new house dynamically (e.g., "VC1").
*   **Intake Date:** Start date of the flock.
*   **Intake Counts:** Number of Male/Female birds.
*   **DOA:** Dead on Arrival counts.

*Note: You cannot create a new flock in a House that already has an Active flock.*

### 3. Daily Data Entry
Go to **Daily Entry** to log data.
*   **House:** Select the active house.
*   **Feed:** Enter "Grams per Bird" for Male and Female.
*   **Water:** Enter the **3 Meter Readings** (as integers, representing cubic meters * 100).
    *   Example: Reading `10500` = `105.00` m³.
    *   The system calculates 24h consumption by comparing Reading 1 of Today vs Yesterday.
*   **Body Weight:** Enter Male/Female weights and uniformity.
*   **Photo:** Upload post-mortem or flock photos.

### 4. Import Data
Go to **Import** to upload an Excel file (`.xlsx`).
*   **Structure:** The file can contain multiple sheets (one per flock).
*   **Metadata:** The system looks for "HOUSE:", "INTAKE DATE:", etc., in the first few rows (B2, B3...).
*   **Data:** Daily data should start from Row 10.
*   **Note:** If House/Flock doesn't exist, it will be created automatically based on the file header.

### 5. Review & Edit
*   Click **History** on the Dashboard or **Manage Flocks** page.
*   View **Performance Charts** (Egg Prod, Mortality, BW).
*   View **Weekly Summary** table.
*   View **Daily Logs** table.
*   Click **Edit** on any log row to correct mistakes.
