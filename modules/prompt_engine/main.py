# modules/prompt_engine/main.py
from langchain_ollama.llms import OllamaLLM
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from modules.embeddings import filter_relevant_contexts
from . import prompt_templates

class PromptAgent:

    def __init__(self, llm_model, embed_model, chroma_db, collection_name):
        self.llm_model = llm_model
        self.embed_model = embed_model
        self.chroma_db = chroma_db
        self.collection_name = collection_name

    def _fetch_context(self, question: str, top_k: int = 6, min_keep: int = 1, debug: bool = False) -> str:
        db = Chroma(
            collection_name=self.collection_name,
            persist_directory=self.chroma_db,
            embedding_function=OllamaEmbeddings(model=self.embed_model)
        )

        # Retrieve top_k documents
        docs = db.similarity_search(question, k=top_k)
        doc_texts = [doc.page_content for doc in docs]

        # Apply smart filter
        filtered_texts = filter_relevant_contexts(
            query=question,
            doc_texts=doc_texts,
            embedding_func=OllamaEmbeddings(model=self.embed_model),
            min_keep=min_keep,
            debug=debug
        )

        return "\n".join(filtered_texts)

    # def resolve(
    #     self,
    #     question: str,
    #     options: list = None,
    #     multi_select: bool = False,
    #     top_k: int = 10,
    #     debug: bool = False
    # ) -> str:
    #     context = self._fetch_context(question, top_k, debug=debug)
    #     llm = OllamaLLM(model=self.llm_model)

    #     if options:
    #         prompt = prompt_templates.options_prompt(context, question, options, multi_select)
    #     else:
    #         prompt = prompt_templates.base_prompt(context, question)

    #     return llm.invoke(prompt).strip()
    
    def resolve(
        self,
        question: str = None,
        options: list = None,
        multi_select: bool = False,
        top_k: int = 10,
        debug: bool = False,
        custom_prompt_fn: callable = None,
        custom_prompt_args: dict = None
    ) -> str:
        llm = OllamaLLM(model=self.llm_model)

        if custom_prompt_fn:
            # Case 1: Metadata-based prompt that doesn’t need embeddings
            if custom_prompt_args and not question and not options:
                prompt = custom_prompt_fn(**custom_prompt_args)

            # Case 2: Context-based prompt function (with or without options)
            else:
                context = self._fetch_context(question, top_k, debug=debug)
                prompt = custom_prompt_fn(
                    context=context,
                    question=question,
                    options=options,
                    multi_select=multi_select
                )
        else:
            # Default path using internal prompt templates
            context = self._fetch_context(question, top_k, debug=debug)
            if options:
                prompt = prompt_templates.options_prompt(context, question, options, multi_select)
            else:
                prompt = prompt_templates.base_prompt(context, question)

        return llm.invoke(prompt).strip()
