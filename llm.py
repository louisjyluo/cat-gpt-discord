import os
import asyncio
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

catClient = OpenAI(api_key=os.getenv('CATSEEK'))
api_request_counter = 0


async def chat(msg):
  global api_request_counter
  api_request_counter += 1
  print(f"API Request Count: {api_request_counter}")

  try:
    user_message = msg.content
    system_prompt = "Make the response sound like a cat replied and do not exceed 200 words under any circumstance."

    response = catClient.chat.completions.create(
      model="gpt-5.2",
      messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
      ]
    )

    assistant_message = response.choices[0].message.content
    await asyncio.sleep(1)

    return assistant_message

  except Exception as e:
    print(f"Error: {e}")
    return "Merrorr: Something went mwrong mmmmmm"