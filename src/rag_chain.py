from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI # langchain wrapper for gemini
from langchain_huggingface import HuggingFaceEmbeddings # loads sentence transformer models from huggingface
from langchain_chroma import Chroma # langchain support for chromadb
from langchain_core.prompts import ChatPromptTemplate # creates structured prompts
from langchain_classic.chains import create_retrieval_chain # builds a rag chain, combines retriever (chroma) and LLM
from langchain_classic.chains.combine_documents import create_stuff_documents_chain # creates chain that combines documents to be sent to LLM

load_dotenv() 

def ask_bot(question: str):
    """Takes a user question, searches ChromaDB, and asks Gemini for the answer."""
    
    # langchain uses declarative programming, so logic might seem backwards
    # but this is just to set up the blueprint
    llm = ChatGoogleGenerativeAI( 
        model="gemini-3.1-flash-lite-preview", 
        temperature=0.7, 
        max_tokens=500
    )
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")    
    vector_store = Chroma(
        collection_name="ftc_team_data",
        persist_directory="./chroma_db",
        embedding_function=embeddings
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": 40}) # take top 5 most relevant chunks
    system_prompt = (
        "You are an expert FIRST Tech Challenge (FTC) scouting assistant. "
        "Use the following retrieved context to answer the user's question. "
        "Here is a translation guide for FTC Seasons: "
        "2018 is 'Rover Ruckus', 2019 is 'Skystone', 2020 is 'Ultimate Goal', "
        "2021 is 'Freight Frenzy', 2022 is 'Powerplay', 2023 is 'Centerstage', "
        "2024 is 'Into the Deep', 2025 is 'Decode'."
        "If the answer is not in the context, say 'I don't have that information.' "
        "Do not make up stats or scores. Keep your answer concise and friendly.\n\n"
        "Context:\n{context}"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    response = rag_chain.invoke({"input": question})
    
    return response["answer"]

if __name__ == "__main__":
    test_question = "What is team 14469's highest score in Powerplay season?"
    answer = ask_bot(test_question)
    print(f"\n{answer}")