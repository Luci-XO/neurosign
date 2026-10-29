"""analysis/neuro_knowledge.py - small offline Q&A fallback for Neuro when Gemini is unavailable.
Keyword-matched, not a real NLP model: good enough to keep the demo alive on bad Wi-Fi."""

ENTRIES = [
    {
        "keywords": ["what is parkinson", "what's parkinson", "define parkinson"],
        "answer": "Parkinson's disease is a progressive condition of the nervous system that mainly affects movement. "
                  "It happens when nerve cells that produce dopamine, a chemical that helps control movement, "
                  "gradually stop working properly. Common signs include tremor, stiffness, and slower movement. "
                  "A doctor is needed for an actual diagnosis.",
    },
    {
        "keywords": ["symptom", "sign", "early sign"],
        "answer": "Common early signs include a slight tremor (often in one hand), stiffness or slowness of movement, "
                  "smaller handwriting, a softer or more monotone voice, and reduced facial expression. Symptoms "
                  "usually develop gradually. If you're noticing these in yourself or someone else, a doctor can "
                  "give an actual evaluation.",
    },
    {
        "keywords": ["cause", "why does", "what causes"],
        "answer": "The exact cause isn't fully understood. It involves the loss of dopamine-producing nerve cells in "
                  "a brain region called the substantia nigra. Both genetic and environmental factors are thought "
                  "to play a role, but for most people there's no single identifiable cause.",
    },
    {
        "keywords": ["treat", "cure", "medication", "levodopa", "therapy"],
        "answer": "There's currently no cure, but symptoms can often be managed well, especially with early treatment. "
                  "Levodopa is the most common medication, it helps replace the dopamine the brain is short on. "
                  "Physical therapy, exercise, and other medications can also help. Treatment decisions should "
                  "always be made with a doctor.",
    },
    {
        "keywords": ["history", "discover", "james parkinson", "1817"],
        "answer": "The condition was first described in 1817 by James Parkinson in an essay called 'An Essay on the "
                  "Shaking Palsy.' It was later named after him by the neurologist Jean-Martin Charcot. The role of "
                  "dopamine was discovered in the late 1950s and 1960s, leading to Levodopa therapy.",
    },
    {
        "keywords": ["tremor", "shake", "shaking"],
        "answer": "Tremor in Parkinson's is often a 'resting tremor' -- it tends to appear when the hand is relaxed "
                  "and still, and can lessen during deliberate movement. It commonly starts on one side of the body. "
                  "Not all tremor is Parkinson's related, so it's worth having it checked by a doctor.",
    },
    {
        "keywords": ["age", "young", "old", "who gets"],
        "answer": "Parkinson's most commonly develops after age 60, but it can occur earlier -- this is sometimes "
                  "called young-onset Parkinson's. Risk generally increases with age.",
    },
]

FALLBACK_ANSWER = (
    "I don't have a prepared answer for that right now (I'm running in offline mode). "
    "I can help with general questions about what Parkinson's disease is, its symptoms, causes, "
    "treatment, or history. For anything about your own health, please see a doctor."
)


def offline_answer(question):
    q = question.lower()
    for entry in ENTRIES:
        if any(kw in q for kw in entry["keywords"]):
            return entry["answer"]
    return FALLBACK_ANSWER