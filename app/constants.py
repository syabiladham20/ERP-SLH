# Constants for fast membership checks
ALLOWED_EXPORT_ROLES = frozenset(['Management', 'Farm'])
FARM_HATCHERY_ADMIN_DEPTS = frozenset(['Farm', 'Hatchery', 'Admin'])
FARM_HATCHERY_ADMIN_MGMT_DEPTS = frozenset(['Farm', 'Hatchery', 'Admin', 'Management'])
ADMIN_FARM_MGMT_ROLES = frozenset(['Admin', 'Farm', 'Management'])

INV_TX_TYPES_ALL = frozenset(['Purchase', 'Usage', 'Adjustment', 'Waste'])
INV_TX_TYPES_USAGE_WASTE = frozenset(['Usage', 'Waste'])

REARING_PHASES = frozenset(['Brooding', 'Growing', 'Pre-lay'])
EMPTY_NOTE_VALUES = frozenset(['none', 'nan'])

# Initial User Data for Seeding
INITIAL_USERS = [
    {'username': 'admin', 'password': 'admin123', 'dept': 'Admin', 'role': 'Admin'},
    {'username': 'farm_user', 'password': 'farm123', 'dept': 'Farm', 'role': 'Worker'},
    {'username': 'hatch_user', 'password': 'hatch123', 'dept': 'Hatchery', 'role': 'Worker'},
    {'username': 'manager', 'password': 'manager123', 'dept': 'Management', 'role': 'Management'}
]

# Define human-readable labels for metrics
METRIC_LABELS = {
    'mortality_female_pct': 'Female Mortality',
    'mortality_male_pct': 'Male Mortality',
    'egg_production_pct': 'Egg Production Rate'
}
