"""
Vector Embedding Blacklist
"""

# Exclude embedding entries - Key containing keyword that are not useful in search. Implemented as partial match. 
exclude_embedding_keys = {"password", "resume"}

"""
Parsing Related Blacklist

> Field Blacklist
> Button Blacklist
> Field-Type Specific Blacklist
> `find_associated_text` label lookup Blacklist
"""

'''Field Blacklist'''
# Full
field_blacklist_id_full = {}
field_blacklist_label_full = {}
field_blacklist_placeholder_full = {}
field_blacklist_attribute_value_full = {}
# Partial
field_blacklist_id_partial = {'skills'}
field_blacklist_label_partial = {'skills', 'robot', 'captcha', 'forgotpassword', 'employee id', 'cookie', 'check to skip', 'country phone code'}
field_blacklist_placeholder_partial = {'search job'}
field_blacklist_attribute_value_partial = {}

'''Button Blacklist'''
# Full
button_blacklist_id_full = {'accountsettingsbutton'}
button_blacklist_label_full = {}
button_blacklist_text_full = {'apply with indeed', 'read more', 'dropbox', 'google drive', 'alerts found', 'back to job posting', 'candidate home', 'job alerts', 'search for jobs', 'settings', 'back'}
button_blacklist_attribute_value_full = {}
# Partial
button_blacklist_id_partial = {'expandbutton', 'collapsebutton', 'settings', 'forgotpassword', 'utility', 'download', 'cookie', 'back button'}
button_blacklist_label_partial = {'cover letter', 'additional document', 'certification', 'license', 'language', 'skills', 'learn more', 'cookie'}
button_blacklist_text_partial = {'google', 'forgot password', 'forgot your password', 'see more', 'show more', 'job posting', 'alert', 'home', 'profile', 'manually', 'cookie', 'cover letter', 'additional document', 'certification', 'license','language', 'skills'}
button_blacklist_attribute_value_partial = {'header', 'menu', 'cookie'}

'''Field-Type Specific Blacklist'''
# Full
text_type_blacklist_full = {}
list_type_blacklist_full = {}
dropdown_type_blacklist_full = {}
dropdown_option_blacklist_full = {''}
multiselect_type_blacklist_full = {}
multiselect_option_blacklist_full = {"Accounting", "Actuarial Science", "Administrative Leadership", "Advertising", "Aerospace Engineering", "African-American Studies", "African Languages, Literatures, and Linguistics", "African Studies", "Agricultural/Biological Engineering and Bioengineering", "Agricultural Business and Management", "Agricultural Economics", "Agricultural Education", "Agricultural Journalism", "Agricultural Mechanization", "Agricultural Technology Management", "Agriculture", "Agronomy and Crop Science", "Air Traffic Control", "American History", "American Literature", "American Sign Language", "American Studies", "Anatomy", "Ancient Studies", "Animal Behavior and Ethology", "Animal Science", "Animation and Special Effects", "Anthropology", "Applied Mathematics", "Applied Physics", "Aquaculture", "Aquatic Biology", "Arabic", "Archeology", "Architectural Engineering", "Architectural History", "Architecture", "Art", "Art Education", "Art History", "Artificial Intelligence and Robotics", "Art Therapy", "Asian-American Studies", "Astronomy", "Astrophysics", "Athletic Training", "Atmospheric Science", "Automotive Engineering", "Aviation", "Bakery Science", "Biblical Studies", "Biochemistry", "Bioethics", "Biology", "Biomedical Engineering", "Biomedical Science", "Biopsychology", "Biotechnology", "Botany/Plant Biology", "Business Administration", "Business Administration/Management", "Business Communications", "Business Education", "Canadian Studies", "Caribbean Studies", "Cell Biology", "Ceramic Engineering", "Ceramics", "Chemical Engineering", "Chemical Physics", "Chemistry", "Child Care", "Child Development", "Chinese", "Chiropractic", "Church Music", "Cinematography and Film/Video Production", "Circulation Technology", "Civil Engineering", "Classics", "Clinical Psychology", "Cognitive Psychology", "Cognitive Science", "Commerce", "Communication Disorders", "Communications Studies/Speech Communication and Rhetoric", "Comparative Literature", "Computer Graphics", "Computer Systems Analysis", "Construction Management", "Counseling", "Crafts", "Creative Writing", "Criminal Science", "Criminology", "Culinary Arts", "Dance", "Data Processing", "Dental Hygiene", "Developmental Psychology", "Diagnostic Medical Sonography", "Dietetics", "Digital Communications and Media/Multimedia", "Drawing", "Early Childhood Education", "East Asian Studies", "East European Studies", "Ecology", "Economics", "Education", "Education Administration", "Educational Psychology", "Education of the Deaf", "Electrical Engineering", "Elementary Education", "Engineering", "Engineering Mechanics", "Engineering Physics", "English", "English Composition", "English Literature", "Entomology", "Entrepreneurship", "Environmental/Environmental Health Engineering", "Environmental Design/Architecture", "Environmental Science", "Epidemiology", "Equine Studies", "Ethnic Studies", "European History", "Experimental Pathology", "Experimental Psychology", "Fashion Design", "Fashion Merchandising", "Feed Science", "Fiber, Textiles, and Weaving Arts", "Film", "Finance", "Floriculture", "Food Science", "Forensic Science", "Forestry", "French", "Furniture Design", "Game Design", "Gay and Lesbian Studies", "Genetics", "Geography", "Geological Engineering", "Geology", "Geophysics", "German", "Gerontology", "Government", "Graphic Design", "Health Administration", "Hebrew", "Hispanic-American, Puerto Rican, and Chicano Studies", "Historic Preservation", "History", "Home Economics", "Horticulture", "Hospitality", "Human Development", "Human Resources Management", "Illustration", "Industrial Design", "Industrial Engineering", "Industrial Management", "Industrial Psychology", "Informatics", "Information Technology", "Interior Architecture", "Interior Design", "International Agriculture", "International Business", "International Relations", "International Studies", "Islamic Studies", "Italian", "Japanese", "Jazz Studies", "Jewelry and Metalsmithing", "Jewish Studies", "Journalism", "Kinesiology", "Korean", "Landscape Architecture", "Landscape Horticulture", "Land Use Planning and Management", "Latin American Studies", "Library Science", "Linguistics", "Logistics Management", "Management Information Systems", "Managerial Economics", "Marine Biology", "Marine Science", "Marketing", "Marketing/Communications", "Massage Therapy", "Mass Communication", "Materials Science", "Mathematics", "Mechanical Engineering", "Medical Technology", "Medieval and Renaissance Studies", "Mental Health Services", "Merchandising and Buying Operations", "Metallurgical Engineering", "Microbiology", "Middle Eastern Studies", "Military Science", "Mineral Engineering", "Missions", "Modern Greek", "Molecular Biology", "Molecular Genetics", "Mortuary Science", "Museum Studies", "Music", "Musical Theater", "Music Education", "Music History", "Music Management", "Music Therapy", "Native American Studies", "Natural Resources Conservation", "Naval Architecture", "Neurobiology", "Neuroscience", "Nuclear Engineering", "Nursing", "Nutrition", "Occupational Therapy", "Ocean Engineering", "Oceanography", "Operations Management", "Organizational Behavior Studies", "Other", "Painting", "Paleontology", "Pastoral Studies", "Peace Studies", "Petroleum Engineering", "Pharmacology", "Pharmacy", "Philosophy", "Photography", "Photojournalism", "Physical Education", "Physical Therapy", "Physician Assistant", "Physics", "Physiological Psychology", "Piano", "Planetary Science", "Plant Pathology", "Playwriting and Screenwriting", "Political Communication", "Political Science", "Portuguese", "Pre-Dentistry", "Pre-Law", "Pre-Medicine", "Pre-Optometry", "Pre-Seminary", "Pre-Veterinary Medicine", "Printmaking", "Psychology", "Public Administration", "Public Health", "Public Policy", "Public Policy Analysis", "Public Relations", "Radio and Television", "Radiologic Technology", "Range Science and Management", "Real Estate", "Recording Arts Technology", "Recreation Management", "Rehabilitation Services", "Religious Studies", "Respiratory Therapy", "Risk Management", "Rural Sociology", "Russian", "Scandinavian Studies", "Sculpture", "Slavic Languages and Literatures", "Social Psychology", "Social Work", "Sociology", "Software Engineering", "Soil ScienceTurfgrass Science", "Sound Engineering", "South Asian Studies", "Southeast Asia Studies", "Spanish", "Special Education", "Speech Pathology", "Sport and Leisure Studies", "Sports Management", "Statistics", "Surveying", "Sustainable Resource Management", "Teacher Education", "Teaching English as a Second Language", "Technical Writing", "Technology Education", "Textile Engineering", "Theatre", "Theology", "Tourism", "Toxicology", "Training and Development", "Urban Planning", "Urban Studies", "Visual Communication", "Voice", "Web Design", "Webmaster and Web Management", "Welding Engineering", "Wildlife Management", "Women's Studies", "Youth Ministries", "Zoology"}
# Partial
text_type_blacklist_partial = {}
list_type_blacklist_partial = {'phone number', 'mobile phone'}
list_option_blacklist_partial = {'select', '--', 'option', 'no item', 'no match', 'referral'}
dropdown_type_blacklist_partial = {}
dropdown_option_blacklist_partial = {'select', '--', 'no option', 'no item', 'no match', '0 option'}
multiselect_type_blacklist_partial = {'country phone code'}
multiselect_xpath_keyword_blacklist_partial= {'promptTitle'}

''' New Elements Blacklist '''
# Buttons
new_button_blacklist_text_full = {}
new_button_blacklist_text_partial = {'read less'}
new_button_blacklist_id_full = {}
new_button_blacklist_id_partial = {'expandbutton', 'collapsebutton'}
# Fields
new_field_blacklist_id_full = {}
new_field_blacklist_id_partial = {}

'''Blacklist that blocks the find_associated_text label-lookup function'''
# Full
find_associated_text_blacklist_id_full = {}
find_associated_text_blacklist_text_full = {'save and continue', 'next'}
# Partial
find_associated_text_blacklist_id_partial = {'pagefooter', 'nextbutton', 'backbutton'}
find_associated_text_blacklist_text_partial = {
    'accept', 'agree', 'apply', 'approve', 'complete', 'continue', 'final', 'finish', 
    'i authorize', 'next', 'proceed', 'review', 'save', 'save & continue', 'save and next', 
    'save and proceed', 'submit', 'submit application', 'accept', 'acknowledge', 'add', 
    'agree', 'confirm', 'continue', 'create', 'create account', 'delete', 'get code', 'get otp', 
    'log in', 'login', 'next', 'register', 'remove', 'save', 'send code', 'send otp', 'sign in', 
    'sign up', 'signin', 'signup', 'submit', 'verify'
}

"""
Other Blacklist
"""

# Options Blacklist
default_options_placeholder_blacklist = ['select', 'results', 'expanded']




