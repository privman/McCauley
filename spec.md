# **Intelligent Conversational Agent** 

## **Overview** 

Create a conversational AI system for collecting feedback from employees at a work place. The feedback can be about a specific colleague, and organisational unit (e.g., a team, department), or the entire organisation. Feedback can be provided anonymously or not (default not).

The agent will help feedback providers put their feedback into the Situation-Behavior-Impact format.

Feedback will be visible to the feedback recipient and their reporting chain. For personal feedback, the named individual is the recipient. For organisational feedback, it's the head of the organisational unit.

Feedback recipients will be able to chat with the agent about all the feedback they have access to and ask it to create reports summarising it.

## **Core Requirements** 

1. Conversational Flow 
* Implement a bot that can engage in natural conversation with users in text and/or voice 
* The bot should be proactive in soliciting feedback, asking guiding questions as a skilled interviewer would to extract as much as possible 
* Extract and validate mentioned entities into a structured format: identify the correct individuals and organisational units mentioned against a structured org representation, store times and timespans in structured fields, and categorise feedback by topic and sentiment
  * When responding to ambiguous entity references, the bot must respond with a disambiguation question, listing possible matches, before continuing the conversation 
* Handle basic error cases and invalid inputs gracefully 
* When collecting feedback, maintain conversation context throughout the interaction using a state machine that tracks the current feedback record and allows switching between records while maintaining a set of incomplete records to be resumed later in the conversation

2. Data Extraction & Storage 
* Store conversations and extracted data in a structured format (JSON) 
* Implement basic data validation for collected information 
* Generate a summary of the conversation with extracted key points 

3. Technical Requirements 
* Use Python for implementation 
* Implement proper error handling
* Implement linting, unit tests, and integration tests
* Architecteture and tool choices should consider the need for scaling the system to hundreds of orgs with up to XXXk users per org, but initial implementation should avoid premature performance optimisation
* Use Anthropic API with Google streaming TTS and STT
* When interacting with feedback recipients, use RAG to retrieve stored feedback, ensuring access is restricted to feedback the recipient should have access to (feedback for themselves, their direct and indirect reports, and organisational units that they head or oversee indirectly)
  * The security of this data access is a critical requirement and must be robust, including to prompt injection and jailbreak attempts, to ensure that users only have access to the feedback that is addressed to them or their reports
* Add sentiment analysis to detect customer frustration 
* Implement multi-turn conversation memory 
* Add support for multiple languages 

# **Deliverables** 

1. Source code in a Git repository 

2. README with: 
* Setup instructions 
* System architecture overview 
* Explanation of key design decisions 
* Description of potential improvements 

3. URL to demo video of sample conversations demonstrating the bot's capabilities
