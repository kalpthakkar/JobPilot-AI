# config/user_data_config.py
from typing import Dict

'''
Match Settings

case-sensitive: False
exact-match: _full (True) | _partial (False)
normalized-whitespace: True
'''
# Enter other possible options (in order) not mentioned in your 'user_data.json' for identifying the answer.
education_degree_full = [
    {'Masters', "Master's Degree"},
    {'Bachelors', "Bachelor's Degree"}
]
education_field_of_study_full = [
    {'Computer and Information Science'},
    {'Computer Science'}
]
# Enter possible options w.r.t answers (in order) not mentioned in your 'user_data.json' for searching the options.
search_option_candidates: Dict[str, list] = {
    "Education": [
        {
            "School or University": {
                'University of Central Florida': ['University of Central Florida','Other']
            },
            "Degree": {
                'Master': ['Master of Science', "Master's Degree"]
            },
            "Field of Study or Major": {
                'Computer Science': ['Computer Science'],
                'Computer and Information Science': ['Computer and Information Science']
            }
        },
        {
            "School or University": {
                'LDRP Institute of Technology and Research': ['LDRP Institute of Technology and Research'],
                'Other': ['Other']
            },
            "Degree": {
                'Bachelor': ['Bachelor of Engineering', "Bachelor's Degree"]
            },
            "Field of Study or Major": {
                'Computer Engineering': ['Computer Engineering'],
                'Computer Science': ['Computer Science', 'Computer and Information Science']
            }
        }
    ]
}

