import os
import sys
from datetime import datetime

# Add the project root to sys.path
sys.path.append('/Users/daathwi/Master/civiccare/civic-care-backend/api/')

from app.services.analytics_pdf import build_performance_report_pdf

def test_generate_pdf():
    # Mock data with long names to test wrapping
    department_rows = [
        {
            "name": "Public Health and Sanitation Department (West Division) - Emergency Response Unit",
            "metrics": {"total": 150, "resolved": 120, "pending": 30, "sla_resolved": 110, "escalated": 5},
            "scores": {"sla_rate": 0.92, "resolution_rate": 0.8, "dpi": 85.5},
            "performance": "Excellent"
        },
        {
            "name": "Water Supply and Sewerage Board (Main Maintenance & Operations)",
            "metrics": {"total": 200, "resolved": 150, "pending": 50, "sla_resolved": 140, "escalated": 10},
            "scores": {"sla_rate": 0.93, "resolution_rate": 0.75, "dpi": 82.0},
            "performance": "Good"
        }
    ]
    
    worker_rows = [
        {
            "name": "Officer Rajesh Kumar Sharma (Senior Lead Field Inspector - Zone 5)",
            "phone": "+91-9876543210",
            "department_name": "Public Health and Sanitation",
            "ward_name": "Ward 45 (Northeastern Industrial Area)",
            "metrics": {"period_resolved": 45, "sla_rate": 0.95, "attendance_rate": 0.88},
            "status": "onduty",
            "designation": "Senior Inspector"
        }
    ]
    
    ward_rows = [
        {
            "id": 1,
            "name": "Industrial Hub and Residential Complex Phase 2",
            "number": 101,
            "zone_name": "West Zone (Primary Industrial Sector)",
            "representative_name": "Hon. Shrimati Meenakshi Subramanian",
            "representative_phone": "9988776655",
            "party_short_code": "AAP",
            "metrics": {"total": 500, "resolved": 450, "pending": 50, "sla_resolved": 440, "escalated": 12},
            "scores": {"resolution_rate": 0.9, "wpi": 88.5},
            "performance": "High"
        }
    ]
    
    zone_rows = [
        {
            "name": "Central Business District and Heritage Zone",
            "code": "CBD-HZ",
            "metrics": {"total": 1000, "resolved": 900, "pending": 100, "sla_resolved": 880},
            "scores": {"resolution_rate": 0.9, "zpi": 89.0},
            "performance": "Robust"
        }
    ]
    
    # Matching the keys used in analytics_pdf.py for escalation
    escalation = {
        "total": 25,
        "reopened_count": 5,
        "by_priority": {"high": 10, "medium": 10, "low": 5},
        "by_zone": [{"name": "Central Zone", "count": 10}],
        "by_department": [{"name": "Sanitation", "count": 15}]
    }
    
    party_control = {
        "parties": [
            {
                "name": "Aam Aadmi Party",
                "short_code": "AAP",
                "color": "#0000FF",
                "ward_count": 10,
                "avg_wpi": 85.0,
                "metrics": {"total": 100, "resolution_pct": 90.0, "sla_pct": 88.0}
            }
        ],
        "wards": [
            {
                "name": "Industrial Hub and Residential Complex Phase 2",
                "number": 101,
                "party_color": "#0000FF"
            }
        ]
    }
    
    sustainability = {"message": "All renewable energy targets for current cycle are on track."}
    ward_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"WardName": "Industrial Hub and Residential Complex Phase 2", "ward_no": "101"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.1, 28.5], [77.2, 28.5], [77.15, 28.6], [77.1, 28.5]]]
                }
            }
        ]
    }
    
    pdf_bytes = build_performance_report_pdf(
        title="Executive Performance Report - March 2026",
        generated_at=datetime.now(),
        filters_note="Filter: All Departments | Period: Last 30 Days",
        department_rows=department_rows,
        worker_rows=worker_rows,
        ward_rows=ward_rows,
        zone_rows=zone_rows,
        escalation=escalation,
        party_control=party_control,
        sustainability=sustainability,
        ward_geojson=ward_geojson,
        citizen_cis={
            "top": [
                {
                    "name": "Test Citizen",
                    "phone": "9999999999",
                    "ward": "Ward A",
                    "zone": "Zone 1",
                    "cis_score": 88.5,
                }
            ],
            "bottom": [{"name": "Low User", "phone": "9000000000", "ward": "–", "zone": "–", "cis_score": 12.0}],
            "week_note": "Sample week note for PDF test.",
        },
    )
    
    output_path = "/tmp/simplified_report.pdf"
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF generated at {output_path}")

if __name__ == "__main__":
    test_generate_pdf()
