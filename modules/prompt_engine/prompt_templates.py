# modules/prompt_engine/prompt_templates.py
from langchain_core.prompts import ChatPromptTemplate

'''
=====================================================================================================
Base Template
=====================================================================================================
'''
def base_prompt(context: str, question: str) -> str:
    template = """You are a helpful assistant answering job application questions.

If relevant information is available in the context below, use it to answer.
If not, rely on reasonable assumptions and common best practices for job applications.
Respond as if you are the applicant. Your answer should be clear, direct, and concise.
Do not mention the context, your reasoning process, or how the answer was formed.

<context>
{context}
</context>

<question>
{question}
</question>

Return a direct short answer without repeating question (Minimum word: 1, Maximum word limit: 10).
"""

    return ChatPromptTemplate.from_template(template).format_messages(
        context=context or "N/A", 
        question=question
    )[0].content


'''
=====================================================================================================
Options Prompt Template
=====================================================================================================
'''
def options_prompt(context: str, question: str, options: list[str], multi_select: bool = False) -> str:

    choices = "\n".join([f"- {opt}" for opt in options])
    
    instruction = (
        "Select *all* options that are most appropriate based on the context and reasonable assumptions."
        if multi_select else
        "Select the *one best option* based on the context and reasonable assumptions."
    )

    template = """You are a helpful assistant that answers job application questions.

If relevant information is available in the context below, use it to select the most appropriate {return_format}.
If not, rely on reasonable assumptions and common best practices for job applications.
Respond as if you are the applicant.

<context>
{context}
</context>

<question>
{question}
</question>

<options>
{choices}
</options>

{instruction}

Return only the exact text of the selected {return_format}, with no explanations or additional comments. Do not repeat the question, and do not mention the context or your reasoning.
If none clearly apply, select the most reasonable {choice_scope} based on typical job application behavior.
Do not mention the context, reasoning process, or how you chose the answer.
"""

    prompt = ChatPromptTemplate.from_template(template)
    
    return prompt.format_messages(
        context=context,
        question=question,
        choices=choices,
        instruction=instruction,
        return_format="options (as a list)" if multi_select else "option",
        choice_scope="one(s)" if multi_select else "one"
    )[0].content

