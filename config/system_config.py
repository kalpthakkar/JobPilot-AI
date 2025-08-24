'''
Match Settings

case-sensitive: False
exact-match: _full (True) | _partial (False)
normalized-whitespace: True
'''
escape_refresh_multiselect_identifiers_partial = {'How Did You Hear About Us?', 'Country / Territory Phone Code'}
escape_refresh_dynamic_list_identifiers_full = {'Country', 'Country*', 'State','State*'}
escape_refresh_dynamic_list_identifiers_partial = {'Country / Territory', 'Phone Extension', 'Phone Device Type'}

'''
Field Categories & Type Identifiers
'''
FIELD_TYPE_IDENTIFIERS_TEXT = {'text', 'textarea', 'email', 'password', 'number', 'url'}
FIELD_TYPE_IDENTIFIERS_RADIO = {'radio'}
FIELD_TYPE_IDENTIFIERS_LIST = {'list'}
FIELD_TYPE_IDENTIFIERS_MULTISELECT = {'multiselect'}
FIELD_TYPE_IDENTIFIERS_CHECKBOX = {'checkbox'}
FIELD_TYPE_IDENTIFIERS_DROPDOWN = {'select'}
FIELD_TYPE_IDENTIFIERS_DATE = {'date', 'datelist'}

'''
FormState -> DESCRIPTION_PAGE
'''
start_apply_btn_identifiers = [ # Search Order Matters (using list)
    'use my last application','autofill with resume', "i'm interested", 'apply', 'apply now'
]

'''
FormState -> AUTH_PAGE
'''
signup_auth_btn_identifiers: set = {'create account', 'sign up', 'signup', 'register', 'create'}
signin_auth_btn_identifiers: set = {'sign in', 'signin', 'log in', 'login'}
verify_auth_btn_identifiers: set = {'verify', 'get otp', 'get code', 'send otp', 'send code'}
other_auth_btn_identifiers: set = {'next', 'submit', 'continue', 'confirm'}
email_verification_page_text_identifiers = {
    "verify your account", "verification email", "email verification", "account verification",
    "confirm your email", "check your email", "we sent you a verification email",
    "confirm your account", "activate your account", "resend verification",
    "email not verified", "awaiting verification", "verify to continue", "unverified account",
    "you must verify your email", "verification pending", "your account needs to be verified"
}
otp_verification_page_text_identifiers = {
    "verification code", "enter the code", "type the code", "receive the code", 
    "received the code", "code was sent"
}

'''
FormState -> LOGGED_IN
'''
progress_btn_identifiers: set = [ # Search Order Matters (using list)
    'submit application', 'submit', 'save & continue', 'save and next', 'save and proceed', 
    'finish', 'apply', 'next', 'continue', 'save', 'review', 'proceed', 'complete', 'final'
]

'''
FormState -> SUBMITTED
'''
application_submitted_page_text_identifiers = {
    'a recruiter will reach out', 'application complete', 'application has been received', 'application has been submitted', 'application received', 
    'application submitted', 'application successfully received', 'application successfully sent', 'if your qualifications match', 
    'someone will get back to you', 'submission complete', 'successfully applied', 'successfully submitted', 'thank you for applying', 
    'thanks for applying', 'thank you for submitting', 'thanks for submitting', 'thank you for your interest', 'thanks for your interest', 
    'thank you for your submission', 'thank you for your application', 'thanks for your application', 'we appreciate your interest', 
    'we will be in touch if', 'we will reach out to you', 'we will reach out if you', 'received your application', 'you have applied', 
    'you have successfully applied', 'application was submitted', 'submitted this application', 'application is under review'
}
already_submitted_page_text_identifiers = {
    'already applied for this', 'already applied to this', 'already been applied', 'already submitted an application', 'application already submitted', 
    'application previously submitted', 'have previously submitted this', 'application submitted previously', 'cannot apply again', 
    "you've already applied", 'you have already applied', 'you have already responded', 'already completed this form', 'already completed this application'
}

'''
Other Identifiers
'''
ack_btn_identifiers: set = {'I authorize', 'acknowledge', 'agree', 'accept', 'approve'}













