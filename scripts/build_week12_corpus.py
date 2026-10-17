from __future__ import annotations

import json

from app.core.config import ROOT_DIR

WEEK12_DIR = ROOT_DIR / "analysis" / "week12"

POLICY_LIMITS = {
    "motor_comprehensive": {"deductible": 1000, "sub_limit": None, "policy_limit": "as declared (IDV)"},
    "motor_third_party": {"deductible": 0, "sub_limit": 750000, "policy_limit": "unlimited (bodily injury)"},
    "property_building": {"deductible": 10000, "sub_limit": None, "policy_limit": "as declared (reinstatement value)"},
    "property_contents": {"deductible": 2500, "sub_limit": None, "policy_limit": "as declared (market value)"},
    "property_burglary": {"deductible": 5000, "sub_limit": 25000, "policy_limit": "as declared"},
}

COVERAGE_IN_FORCE = {
    "MOTOR-COMP-101": {"start_date": "2024-02-01", "end_date": "2025-01-31"},
    "MOTOR-COMP-102": {"start_date": "2024-06-01", "end_date": "2025-05-31"},
    "MOTOR-COMP-103": {"start_date": "2023-09-01", "end_date": "2024-08-31"},
    "MOTOR-COMP-104": {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    "MOTOR-COMP-105": {"start_date": "2024-03-01", "end_date": "2025-02-28"},
    "MOTOR-COMP-106": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
    "MOTOR-TP-201": {"start_date": "2024-04-01", "end_date": "2025-03-31"},
    "MOTOR-TP-202": {"start_date": "2024-07-01", "end_date": "2025-06-30"},
    "PROP-BLDG-301": {"start_date": "2023-06-01", "end_date": "2024-05-31"},
    "PROP-BLDG-302": {"start_date": "2024-06-01", "end_date": "2025-05-31"},
    "PROP-BLDG-303": {"start_date": "2024-11-01", "end_date": "2025-10-31"},
    "PROP-BLDG-304": {"start_date": "2024-01-15", "end_date": "2025-01-14"},
    "PROP-BLDG-305": {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    "PROP-BLDG-306": {"start_date": "2024-02-01", "end_date": "2025-01-31"},
    "PROP-CONT-401": {"start_date": "2024-05-01", "end_date": "2025-04-30"},
    "PROP-CONT-402": {"start_date": "2024-08-01", "end_date": "2025-07-31"},
    "PROP-CONT-403": {"start_date": "2023-12-01", "end_date": "2024-11-30"},
    "PROP-CONT-404": {"start_date": "2024-09-01", "end_date": "2025-08-31"},
}

# reason_code is GROUND TRUTH ONLY — used by the eval judge/grader, never shown to the agent.
CLAIMS = [
    {
        "claim_number": "CLM-2027-00301", "policy_number": "MOTOR-COMP-101", "product": "motor_comprehensive",
        "loss_date": "2024-08-11", "claimed_amount": 220000,
        "fnol_text": "Insured reports vehicle engine seized after driving through a flooded underpass during heavy rain.",
        "adjuster_notes": "Caller: Rakesh Mehta, 14 Lotus Apartments, Andheri West, Mumbai. No injuries. Vehicle towed to network garage. No Engine & Gearbox Protection (IMT-29) endorsement on file.",
        "photo_caption": "Water line visible on lower door panel; engine bay shows water ingress residue.",
        "reason_code": "DENIED_NO_IMT29", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00302", "policy_number": "MOTOR-COMP-102", "product": "motor_comprehensive",
        "loss_date": "2025-02-03", "claimed_amount": 18500,
        "fnol_text": "Insured reversed into a concrete pillar in a mall parking lot, denting the rear bumper and taillight.",
        "adjuster_notes": "Caller: Priya Nair, 22 Green Park Road, Kochi. No injuries, no third party. Straightforward own-damage repair.",
        "photo_caption": "Rear bumper dented, left taillight cracked, no other visible damage.",
        "reason_code": "COVERED_STANDARD_OD", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00303", "policy_number": "MOTOR-COMP-103", "product": "motor_comprehensive",
        "loss_date": "2024-03-15", "claimed_amount": 12000,
        "fnol_text": "Insured holds IMT-28 Zero Dep cover; pothole accident damaged the front-left tyre and bumper in the same incident.",
        "adjuster_notes": "Caller: Suresh Iyer, 9 MG Road, Pune. No injuries. Insured expects full reimbursement on the tyre under Zero Dep.",
        "photo_caption": "Front-left tyre sidewall torn, front bumper scraped.",
        "reason_code": "PARTIAL_TYRE_DEPRECIATION", "ground_truth_status": "partial",
    },
    {
        "claim_number": "CLM-2027-00304", "policy_number": "MOTOR-COMP-104", "product": "motor_comprehensive",
        "loss_date": "2025-03-20", "claimed_amount": 65000,
        "fnol_text": "Insured collided with a road divider late at night.",
        "adjuster_notes": "Caller: Vikram Singh, 5 Civil Lines, Jaipur. Breathalyzer report on file confirms the insured was driving under the influence of alcohol at the time of the accident. No injuries to third parties.",
        "photo_caption": "Front-right quarter panel crushed against divider.",
        "reason_code": "DENIED_DUI", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00305", "policy_number": "MOTOR-COMP-105", "product": "motor_comprehensive",
        "loss_date": "2024-12-28", "claimed_amount": 800000,
        "fnol_text": "Insured's vehicle was stolen from a parking lot; police have not yet issued a Non-Traceable Certificate.",
        "adjuster_notes": "Caller: Anjali Rao, 18 Residency Road, Bengaluru. Theft reported 3 days after discovery. NTC pending.",
        "photo_caption": "No photo — vehicle not recovered.",
        "reason_code": "PENDING_NTC", "ground_truth_status": "pending",
    },
    {
        "claim_number": "CLM-2027-00306", "policy_number": "MOTOR-COMP-106", "product": "motor_comprehensive",
        "loss_date": "2026-01-10", "claimed_amount": 45000,
        "fnol_text": "Insured's car was hit by a falling tree branch during a storm.",
        "adjuster_notes": "Caller: Deepa Krishnan, 3 Lake View, Chennai. Note: policy coverage window should be checked against loss date before proceeding.",
        "photo_caption": "Roof dented, windshield cracked.",
        "reason_code": "REFER_POLICY_LAPSED", "ground_truth_status": "pending",
    },
    {
        "claim_number": "CLM-2027-00307", "policy_number": "MOTOR-TP-201", "product": "motor_third_party",
        "loss_date": "2024-09-05", "claimed_amount": 500000,
        "fnol_text": "Insured's vehicle struck a pedestrian at a crosswalk; third-party bodily injury claim filed.",
        "adjuster_notes": "Caller: Arjun Desai, 11 Model Town, Delhi. Third party: pedestrian sustained a fractured leg, hospitalised 4 days.",
        "photo_caption": "Front bumper scuff, no major vehicle damage.",
        "reason_code": "COVERED_TP_BI", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00308", "policy_number": "MOTOR-TP-202", "product": "motor_third_party",
        "loss_date": "2025-05-12", "claimed_amount": 90000,
        "fnol_text": "Insured's vehicle scraped a parked third-party car while reversing.",
        "adjuster_notes": "Caller: Meera Pillai, 7 Church Street, Bengaluru. No injuries. Third-party vehicle has a dented door.",
        "photo_caption": "Third-party car driver-side door dented and scraped.",
        "reason_code": "COVERED_TP_PD", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00309", "policy_number": "PROP-BLDG-301", "product": "property_building",
        "loss_date": "2024-07-28", "claimed_amount": 350000,
        "fnol_text": "Sudden flash flood following cyclonic rainfall inundated the ground floor of the insured building.",
        "adjuster_notes": "Caller: Rajesh Kumar, 2 Park Street, Kolkata. Water entered within hours during the storm; no history of prior seepage.",
        "photo_caption": "Waterline approximately 2 feet up the ground-floor walls; furniture water-damaged.",
        "reason_code": "COVERED_FLOOD_2023_WORDING", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00310", "policy_number": "PROP-BLDG-302", "product": "property_building",
        "loss_date": "2024-08-11", "claimed_amount": 420000,
        "fnol_text": "Flooding from a nearby river overflow during heavy monsoon rain damaged the ground floor of the insured house.",
        "adjuster_notes": "Caller: Sunita Verma, 44 Civil Lines, Lucknow. Sudden river overflow, not a gradual leak. No IAP-20 Flood Extension Rider on file — insured did not know one existed.",
        "photo_caption": "Mud line on interior walls, flooring warped.",
        "reason_code": "COVERED_FLOOD_2023_WORDING", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00311", "policy_number": "PROP-BLDG-303", "product": "property_building",
        "loss_date": "2025-02-14", "claimed_amount": 280000,
        "fnol_text": "Sudden flooding from a burst municipal drain inundated the insured building's ground floor.",
        "adjuster_notes": "Caller: Mohan Das, 6 Residency Road, Hyderabad. Sudden event, not gradual seepage. No IAP-20 Flood Extension Rider on file.",
        "photo_caption": "Visible water damage to plaster and flooring, ground floor only.",
        "reason_code": "DENIED_FLOOD_2025_WORDING_NO_RIDER", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00312", "policy_number": "PROP-BLDG-304", "product": "property_building",
        "loss_date": "2025-01-02", "claimed_amount": 310000,
        "fnol_text": "Sudden flash flood damaged the ground floor of the insured building two days into the new year.",
        "adjuster_notes": "Caller: Kavita Joshi, 19 Boat Club Road, Pune. Sudden event. No IAP-20 Flood Extension Rider on file. Loss date is just after the 2025 wording took effect.",
        "photo_caption": "Water damage to ground-floor flooring and lower walls.",
        "reason_code": "DENIED_FLOOD_2025_WORDING_NO_RIDER", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00313", "policy_number": "PROP-BLDG-304", "product": "property_building",
        "loss_date": "2024-12-30", "claimed_amount": 305000,
        "fnol_text": "Sudden flash flood damaged the ground floor of the insured building two days before year end.",
        "adjuster_notes": "Caller: Kavita Joshi, 19 Boat Club Road, Pune. Sudden event, same incident type as a near-identical claim filed two days later under the new wording — this one's loss date falls before the cutover.",
        "photo_caption": "Water damage to ground-floor flooring and lower walls, same property as CLM-2027-00312.",
        "reason_code": "COVERED_FLOOD_2023_WORDING", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00314", "policy_number": "PROP-BLDG-305", "product": "property_building",
        "loss_date": "2025-06-01", "claimed_amount": 190000,
        "fnol_text": "Gradual seepage through the foundation over several weeks caused damage to the ground floor.",
        "adjuster_notes": "Caller: Farhan Ali, 8 Alkapuri, Vadodara. Insured admits the dampness had been visible for months before reporting.",
        "photo_caption": "Damp staining and mould along the base of interior walls.",
        "reason_code": "DENIED_GRADUAL_SEEPAGE", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00315", "policy_number": "PROP-BLDG-306", "product": "property_building",
        "loss_date": "2024-09-22", "claimed_amount": 150000,
        "fnol_text": "A kitchen fire damaged part of the building structure; no neighbouring or tenant property was involved.",
        "adjuster_notes": "Caller: Geeta Reddy, 27 Jubilee Hills, Hyderabad. Standard building cover only, no endorsements relevant.",
        "photo_caption": "Charred kitchen ceiling and cabinets, smoke damage to adjacent hallway.",
        "reason_code": "COVERED_FIRE", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00316", "policy_number": "PROP-CONT-401", "product": "property_contents",
        "loss_date": "2024-10-05", "claimed_amount": 60000,
        "fnol_text": "Insured's home was burgled overnight; the back door was left unlocked, no signs of forced or violent entry.",
        "adjuster_notes": "Caller: Nitin Chawla, 12 Sector 21, Noida. Electronics stolen from the living room.",
        "photo_caption": "Back door intact, no pry marks; missing television and laptop.",
        "reason_code": "DENIED_UNFORCED_ENTRY", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00317", "policy_number": "PROP-CONT-402", "product": "property_contents",
        "loss_date": "2025-04-18", "claimed_amount": 45000,
        "fnol_text": "Insured's home was burgled overnight; forced entry via a broken window.",
        "adjuster_notes": "Caller: Shalini Bhatt, 31 Koregaon Park, Pune. Window glass broken, signs of forced entry confirmed by police report.",
        "photo_caption": "Broken window pane, glass fragments inside the room, jewellery box missing.",
        "reason_code": "COVERED_FORCED_ENTRY_SUBLIMIT", "ground_truth_status": "partial",
    },
    {
        "claim_number": "CLM-2027-00318", "policy_number": "PROP-CONT-403", "product": "property_contents",
        "loss_date": "2024-11-30", "claimed_amount": 38000,
        "fnol_text": "Sudden flood from a burst water tank damaged household contents on the ground floor.",
        "adjuster_notes": "Caller: Ramesh Pillai, 5 Marine Drive, Mumbai. Sudden event, contents damaged, not a gradual leak.",
        "photo_caption": "Water-damaged furniture and electronics on the ground floor.",
        "reason_code": "COVERED_FLOOD_2023_WORDING", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00319", "policy_number": "PROP-CONT-404", "product": "property_contents",
        "loss_date": "2025-07-19", "claimed_amount": 42000,
        "fnol_text": "Sudden flood from a burst water tank damaged household contents on the ground floor.",
        "adjuster_notes": "Caller: Ramesh Pillai, 5 Marine Drive, Mumbai. Same type of incident as a prior claim, but under the renewed policy this year. No IAP-20 Flood Extension Rider on file.",
        "photo_caption": "Water-damaged furniture and electronics on the ground floor.",
        "reason_code": "DENIED_FLOOD_2025_WORDING_NO_RIDER", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00320", "policy_number": "PROP-BLDG-306", "product": "property_building",
        "loss_date": "2026-03-01", "claimed_amount": 500000,
        "fnol_text": "Earthquake caused structural cracks in the insured building.",
        "adjuster_notes": "Caller: Harish Nambiar, 14 Anna Nagar, Chennai. No Earthquake Extension (IAP-01) endorsement on file. Also: coverage window should be verified against this loss date.",
        "photo_caption": "Visible diagonal cracking on the main load-bearing wall.",
        "reason_code": "REFER_POLICY_LAPSED", "ground_truth_status": "pending",
    },
    {
        "claim_number": "CLM-2027-00321", "policy_number": "PROP-BLDG-302", "product": "property_building",
        "loss_date": "2024-12-31", "claimed_amount": 260000,
        "fnol_text": "Sudden flash flood damaged the ground floor on the last day of the year.",
        "adjuster_notes": "Caller: Sunita Verma, 44 Civil Lines, Lucknow. Sudden event, one day before the new exclusion wording takes effect. No IAP-20 Flood Extension Rider on file.",
        "photo_caption": "Water damage to ground-floor flooring.",
        "reason_code": "COVERED_FLOOD_2023_WORDING", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00322", "policy_number": "PROP-BLDG-305", "product": "property_building",
        "loss_date": "2025-01-01", "claimed_amount": 265000,
        "fnol_text": "Sudden flash flood damaged the ground floor on the first day the new policy year's wording applies.",
        "adjuster_notes": "Caller: Farhan Ali, 8 Alkapuri, Vadodara. Sudden event, exactly the day the new exclusion wording takes effect. No IAP-20 Flood Extension Rider on file.",
        "photo_caption": "Water damage to ground-floor flooring, same type of loss as a near-identical claim filed one day earlier.",
        "reason_code": "DENIED_FLOOD_2025_WORDING_NO_RIDER", "ground_truth_status": "denied",
    },
    {
        "claim_number": "CLM-2027-00323", "policy_number": "MOTOR-COMP-102", "product": "motor_comprehensive",
        "loss_date": "2025-03-10", "claimed_amount": 15000,
        "fnol_text": "Windshield cracked from a stone chip on the highway.",
        "adjuster_notes": "Caller: Priya Nair, 22 Green Park Road, Kochi. Insured holds glass breakage cover and is not claiming any other damage.",
        "photo_caption": "Single crack across the windshield, no other damage.",
        "reason_code": "COVERED_GLASS_WAIVED_DEDUCTIBLE", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00324", "policy_number": "MOTOR-COMP-105", "product": "motor_comprehensive",
        "loss_date": "2024-11-14", "claimed_amount": 1200000,
        "fnol_text": "Insured's car was hit by a truck; repair estimate exceeds the vehicle's declared value.",
        "adjuster_notes": "Caller: Anjali Rao, 18 Residency Road, Bengaluru. Insured wants to know how the payout will be calculated for a total loss. Third-party truck driver uninjured.",
        "photo_caption": "Vehicle frame bent, front and rear crumple zones both compromised.",
        "reason_code": "COVERED_TOTAL_LOSS_IDV", "ground_truth_status": "covered",
    },
    {
        "claim_number": "CLM-2027-00325", "policy_number": "PROP-CONT-401", "product": "property_contents",
        "loss_date": "2024-06-03", "claimed_amount": 15000,
        "fnol_text": "Jewellery reported missing from the home; insured cannot say exactly when it disappeared.",
        "adjuster_notes": "Caller: Nitin Chawla, 12 Sector 21, Noida. No evidence of forced entry or theft — mysterious disappearance.",
        "photo_caption": "No photo — nature of loss is a missing-item report, not visible damage.",
        "reason_code": "DENIED_MYSTERIOUS_DISAPPEARANCE", "ground_truth_status": "denied",
    },
]


def main() -> None:
    WEEK12_DIR.mkdir(parents=True, exist_ok=True)
    (WEEK12_DIR / "claims_corpus.json").write_text(json.dumps(CLAIMS, indent=2, ensure_ascii=False), encoding="utf-8")
    (WEEK12_DIR / "policy_limits.json").write_text(json.dumps(POLICY_LIMITS, indent=2, ensure_ascii=False), encoding="utf-8")
    (WEEK12_DIR / "coverage_in_force.json").write_text(json.dumps(COVERAGE_IN_FORCE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(CLAIMS)} claims, {len(POLICY_LIMITS)} products, {len(COVERAGE_IN_FORCE)} policies.")


if __name__ == "__main__":
    main()
