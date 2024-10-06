from flask import Flask, jsonify, request, render_template
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import tiktoken
import os
# Load environment variables from .env file
load_dotenv()

try:
    api_key = os.getenv("OPENAI_API_KEY")
    class Config:
        SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')  # Load DB URL from .env
        SQLALCHEMY_TRACK_MODIFICATIONS = False
except Exception as e:
    raise (e)

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# Creating db to save and load description and extraction feilds.
class Extract_details(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(3000), nullable=True)
    extrcation_feilds = db.Column(db.String(3000), nullable=True)
    def __repr__(self):
        return f'<User {self.id}>'

# Function to load llm
def init_llm():
    llm = ChatOpenAI(api_key = api_key, model="gpt-4o", temperature=0.1, max_tokens=4056)
    template = """
    You are an underwriter responsible for analyzing a `{doc_type}` document. Your task is to extract and accurately map relevant details based on the provided guidelines while ensuring consistency with previously extracted fields.

    **Context:**  
    {context}

    ---

    **Fields to Extract:**  
    Identify and map the extraction fields, considering previously extracted details to ensure consistency.  
    {extraction_fields}

    ---

    **Guidelines for Extraction:**  
    {description}

    ---

    **Output Requirements:**  
    Return the extracted information in JSON format as key-value pairs. Each key must correspond to a specific field, and the value should be directly derived from the context. If any fields are missing or cannot be mapped, return the value as "NA." Ensure the output is concise and adheres to the specified format—no additional comments or extraneous text.

    ---

    **Extraction Process:**
    1. **Identify Relevant Fields:** Analyze the provided context and identify the fields to be extracted.
    2. **Leverage Previous Mappings:** Map any relevant or similar extraction fields from prior iterations to maintain consistency.
    3. **Context-Only Extraction:** Extract values solely based on the provided context without making assumptions or using external information.
    4. **Use Guidelines for Accuracy:** Apply the extraction guidelines to map fields with precision.
    5. **Output in JSON:** Ensure the output adheres to the specified JSON format with no additional text, comments, or formatting.
    6. **Missing Fields:** Return "NA" as the value for any fields not found in the context.

    """

    prompt = PromptTemplate(
        input_variables=["doc_type", "context", "description" 'extraction_fields', 'output'],
        template=template,
    )
    llm_chain = prompt | llm
    return llm_chain

try:
    llm_chain = init_llm()
except Exception as e:
    raise (e)

# function to chunk the context within the token limit
def split_text_by_token_limit(text: str, description: str,  model_name: str = "gpt-4o", token_limit: int = 3500):
    # Initialize the tokenizer for the given model
    encoding = tiktoken.encoding_for_model(model_name)

    # Encode the text to get tokens
    tokens = encoding.encode(text)
    all_token = encoding.encode(text+description)
    
    # If token count exceeds the limit, split the tokens
    token_chunks = [tokens[i:i + token_limit] for i in range(0, len(all_token), token_limit)]

    # Decode each chunk back into text
    text_chunks = [encoding.decode(chunk) for chunk in token_chunks]

    return text_chunks

# DB query to add details
def add_details(type, deatils):
    with app.app_context():  # Set up application context
        if type == 'feilds':
            new_details = Extract_details(extrcation_feilds=deatils)
        else:
            new_details = Extract_details(description=deatils)
        db.session.add(new_details)
        db.session.commit()

def get_details(type: str):
    if type == 'extrcation_feilds':
        data = (db.session.query(Extract_details)
                                .filter(Extract_details.extrcation_feilds.isnot(None), Extract_details.extrcation_feilds != '')
                            ).with_entities(Extract_details.extrcation_feilds).all()[-1][0]
    else:
        data = (db.session.query(Extract_details)
                                .filter(Extract_details.description.isnot(None), Extract_details.description != '')
                            ).with_entities(Extract_details.description).all()[-1][0]
    return data
#API to upload content, extraction feilds and description from user. Also display the result
@app.route('/', methods = ['GET', 'POST'])
def dashboard():
    try: 
        # request method access from in html POST
        if request.method == 'POST':
            if request.form.get("extraction_feilds"):
                extraction_feilds = request.form.get("extraction_feilds")
                add_details('feilds', extraction_feilds)

            if request.form.get("description"):
                description = request.form.get("description")
                add_details('description', description)

            if request.form.get("doc_type") and request.form.get("context"):
                
                # Getting the details from html.
                doc_typ = request.form.get("doc_type")
                context = request.form.get("context")

                # Get the latest extraction feilds. If not returns error.
                try:
                    extraction_feilds = get_details('extrcation_feilds')
                except:
                    return render_template('dashboard.html', response = 'No present or history of extraction details') 
                
                # If no description available, LLM extrcat data without description.
                try:
                    description = get_details('description')
                except:
                    description = ''
                
                # chunking the content using `split_text_by_token_limit` function
                context = split_text_by_token_limit(context, description+extraction_feilds)
                # chain of thoughts to get details from all content.
                for i in context:
                    extraction_feilds = llm_chain.invoke({
                    "doc_type": doc_typ,
                    "context": i,
                    "extraction_fields": extraction_feilds,
                    "description": description,
                    "output": '{date: 12/02/2024}'
                    })

                    # extrcating the content to pass in COT
                    extraction_feilds = extraction_feilds.content
                return render_template('dashboard.html', response = (extraction_feilds))
        return render_template('dashboard.html')
    except Exception as e:
        return render_template('dashboard.html', response = e)



if __name__ == "__main__":
    with app.app_context():
        db.create_all()  
    app.run(debug=True)