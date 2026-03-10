import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI # langchain wrapper for gemini
from langchain_huggingface import HuggingFaceEmbeddings # loads sentence transformer models from huggingface
from langchain_chroma import Chroma # langchain support for chromadb
from langchain_core.prompts import ChatPromptTemplate # creates structured prompts
from langchain_classic.chains import create_retrieval_chain # builds a rag chain, combines retriever (chroma) and LLM
from langchain_classic.chains.combine_documents import create_stuff_documents_chain # creates chain that combines documents to be sent to LLM
from data_retrieval import fetch_teams_by_region
load_dotenv() 

STOP_WORDS = {"chances", "beating", "vs", "versus", 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'}

def extract_info(question: str, region_teams_dict: dict):
    teams_mentioned = set()

    # Check for team numbers first
    valid_numbers = set(str(v) for v in region_teams_dict.values())
    found_numbers = re.findall(r'\b\d+\b', question)
    for num in found_numbers:
        if num in valid_numbers:
            teams_mentioned.add(int(num))

    # dict for the region (O(1) lookups)
    clean_names_dict = {}
    for raw_name, number in region_teams_dict.items():
        # Remove in-name punctuation for consistency
        clean_name = re.sub(r"['\-\._]", "", raw_name.lower())
        words = re.findall(r'\b[a-z0-9]+\b', clean_name)
        if words:
            joined_name = " ".join(words)
            
            # for very specific edge cases where two names are the same (ex: RoboKnights and Robo-Knights, bro why)
            if joined_name not in clean_names_dict:
                clean_names_dict[joined_name] = [int(number)]
            else:
                clean_names_dict[joined_name].append(int(number))

    # remove punctuation from question for consistency
    clean_q = re.sub(r"['\-\._]", "", question.lower())
    q_words = re.findall(r'\b[a-z0-9]+\b', clean_q)

    used_indices = set()
    max_ngram_length = 5

    for n in range(max_ngram_length, 0, -1):
        for i in range(len(q_words) - n + 1):
            
            # Skip if any word in this chunk is already claimed by a longer team name
            if any(idx in used_indices for idx in range(i, i + n)):
                continue
                
            ngram = " ".join(q_words[i:i+n])
            
            # Check if phrase is in the team dict and not a stop word
            if ngram in clean_names_dict and ngram not in STOP_WORDS:
                for team_num in clean_names_dict[ngram]:
                    teams_mentioned.add(team_num)
                
                # lock these words so they can't trigger similar words
                for idx in range(i, i + n):
                    used_indices.add(idx)

    return list(teams_mentioned)

def ask_bot(question: str):
    """Takes a user question, searches ChromaDB, and asks Gemini for the answer."""
    
    # langchain uses declarative programming, so logic might seem backwards
    # but this is just to set up the blueprint
    llm = ChatGoogleGenerativeAI( 
        model="gemini-3.1-flash-lite-preview", 
        temperature=0.8, 
        max_tokens=500
    )
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")    
    vector_store = Chroma(
        collection_name="ftc_team_data",
        persist_directory="./chroma_db",
        embedding_function=embeddings
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": 40}) # take top most relevant chunks
    system_prompt = (
        "You are an expert FIRST Tech Challenge (FTC) scouting assistant. "
        "Use the following retrieved context to answer the user's question. "
        
        "Do not make up stats or scores. Keep your answer concise and friendly.\n\n"
        "Always include the team number, season, and region in the top of your response. "
        "Ex: [Number: 14469, Season: Skystone 2020, Region: IL]"
        "If no team number, season, or region is added, put None for that category specifically."
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
    # test_question = "What is team 14469's highest score in Powerplay season?"
    # answer = ask_bot(test_question)
    # print(f"\n{answer}")

    test_multi_team_question = "What is team How chances of beating technophobia, meta infinity, and roboknights?"
    answer = extract_info(test_multi_team_question, fetch_teams_by_region('USIL'))
    print(f"\n{answer}")