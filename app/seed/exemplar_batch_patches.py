"""
Batch updates: simplified input schemas and exemplar_input/output for templates
that were missing Show exemplar previews.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

EXEMPLAR_BATCH_PATCHES: Dict[str, Dict[str, Any]] = {
    "sel_activity": {
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 12,
                    "title": "Grade",
                    "description": "0 = Kindergarten, 1–12 for grade levels.",
                },
                "topic": {
                    "type": "string",
                    "title": "Topic",
                    "description": "What SEL focus? e.g. Start-of-year community building",
                    "format": "textarea",
                    "maxLength": 500,
                },
                "time_duration_minutes": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 120,
                    "title": "Time (minutes)",
                },
            },
            "required": ["grade", "topic", "time_duration_minutes"],
        },
        "context": (
            "Output must match output_schema. Create a culturally sensitive SEL activity with title, "
            "purpose, grouping, materials, clear steps, reflection prompts, differentiation, bloom alignment, "
            "and teacher notes. Keep language inclusive and practical for international classrooms."
        ),
        "exemplar_input": {
            "grade": 7,
            "topic": "Start-of-year community building in a new class",
            "time_duration_minutes": 20,
        },
        "exemplar_output": {
            "title": "Find Your Common Ground",
            "purpose": "Students discover shared interests safely and build early trust in a new class community.",
            "time_needed": 20,
            "grouping": "Small groups of 4",
            "materials": ["Sticky notes", "Markers"],
            "steps": [
                "Each student writes three low-risk facts (favorite food, hobby, music) on sticky notes.",
                "In groups, students sort notes into shared vs unique categories.",
                "Groups write one 'We are the kind of group that…' statement from shared items.",
                "Each group shares their statement with the class.",
            ],
            "reflection_prompts": [
                "What did you learn about a classmate that surprised you?",
                "How can shared interests help teamwork this year?",
            ],
            "differentiation": {
                "support": [
                    "Provide a list of safe prompt choices.",
                    "Allow written sharing instead of speaking out loud.",
                ],
                "extension": [
                    "Groups set one teamwork norm based on what they learned.",
                    "Connect shared interests to a semester group goal.",
                ],
            },
            "bloom_alignment": {
                "level": "Understand",
                "note": "Students explain connections and perspectives rather than only listing facts.",
            },
            "teacher_notes": [
                "Keep prompts low-risk to protect privacy and cultural comfort.",
                "Model inclusive examples before students write.",
            ],
        },
    },
    "lesson_planner": {
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "enum": ["english", "math", "science", "social_studies", "steam", "other"],
                    "title": "Subject",
                },
                "grade": {"type": "integer", "minimum": 0, "maximum": 12, "title": "Grade"},
                "topic": {"type": "string", "title": "Topic", "maxLength": 300},
                "learning_objective": {"type": "string", "title": "Learning objective", "maxLength": 400},
                "time_duration_minutes": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 480,
                    "title": "Duration (minutes)",
                },
                "bloom_level": {"type": "string", "title": "Bloom level"},
            },
            "required": [
                "subject",
                "grade",
                "topic",
                "learning_objective",
                "time_duration_minutes",
                "bloom_level",
            ],
        },
        "exemplar_input": {
            "subject": "english",
            "grade": 8,
            "topic": "Identifying theme in short fiction",
            "learning_objective": "Students identify a theme and support it with two text quotes.",
            "time_duration_minutes": 45,
            "bloom_level": "Analyze",
        },
        "exemplar_output": {
            "title": "Finding the Theme",
            "overview": "Students analyze how authors develop theme through details in a short story excerpt.",
            "learning_objectives": [
                "Identify the theme of a short story.",
                "Support the theme with textual evidence.",
            ],
            "lesson_flow": [
                {"phase": "Hook", "minutes": 5, "activity": "Quote discussion related to choices and consequences."},
                {"phase": "Instruction", "minutes": 10, "activity": "Model identifying theme in a short passage."},
                {"phase": "Guided Practice", "minutes": 15, "activity": "Whole-class analysis of a shared text."},
                {"phase": "Independent Practice", "minutes": 15, "activity": "Students identify theme and evidence in a new excerpt."},
                {"phase": "Closure", "minutes": 5, "activity": "Exit ticket: state the theme and one supporting quote."},
            ],
            "assessment": {
                "type": "exit_ticket",
                "description": "Students state the theme and provide two supporting quotes.",
            },
            "differentiation": {
                "support": [
                    "Provide annotated text and sentence stems for citing evidence.",
                ],
                "extension": [
                    "Compare two possible themes and argue which is stronger using evidence.",
                ],
            },
            "bloom_alignment": {
                "level": "Analyze",
                "note": "Students interpret theme and justify using textual evidence.",
            },
            "standards_alignment": "Aligned to grade 8 reading literature standards for theme and evidence.",
        },
    },
    "learning_activity": {
        "exemplar_input": {
            "subject": "science",
            "grade": 7,
            "topic": "Food chains and energy transfer",
            "time_duration_minutes": 30,
            "bloom_level": "Analyze",
            "activity_type": "hands_on",
            "materials": ["Chart paper", "Markers", "Species cards"],
        },
        "exemplar_output": {
            "title": "Food Web Disruption Game",
            "time_needed": 30,
            "learning_goal": "Analyze relationships and predict effects when one organism is removed from a food web.",
            "materials": ["Chart paper", "Markers", "Species cards"],
            "steps": [
                "Groups build a food web using species cards.",
                "Remove one organism and predict impacts on two other species.",
                "Share predictions and justify with cause-effect reasoning.",
            ],
            "assessment": "Each group explains one predicted impact using vocabulary from the food web.",
            "differentiation": {
                "support": ["Provide a partially completed food web."],
                "extension": ["Add a climate stressor and predict combined effects."],
            },
            "bloom_alignment": {
                "level": "Analyze",
                "note": "Students examine cause-effect relationships in ecosystem interactions.",
            },
        },
    },
    "inquiry_lesson_planner": {
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "enum": ["english", "math", "science", "social_studies", "steam", "other"],
                    "title": "Subject",
                },
                "grade": {"type": "integer", "minimum": 0, "maximum": 12, "title": "Grade"},
                "topic": {"type": "string", "title": "Topic", "maxLength": 300},
                "learning_objective": {"type": "string", "title": "Learning objective", "maxLength": 400},
                "time_duration_minutes": {"type": "integer", "minimum": 5, "maximum": 480, "title": "Time (minutes)"},
                "bloom_level": {"type": "string", "title": "Bloom level"},
            },
            "required": ["subject", "grade", "topic", "learning_objective", "time_duration_minutes", "bloom_level"],
        },
        "exemplar_input": {
            "subject": "science",
            "grade": 8,
            "topic": "Human impact on ecosystems",
            "learning_objective": "Students construct an evidence-based argument about human impact on biodiversity.",
            "time_duration_minutes": 50,
            "bloom_level": "Analyze",
        },
        "exemplar_output": {
            "title": "How Do Humans Change Ecosystems?",
            "driving_question": "How can one human activity disrupt an ecosystem, and what should be done about it?",
            "overview": "Students investigate case studies and produce a claim supported by evidence and reasoning.",
            "lesson_flow": [
                {
                    "phase": "Engage",
                    "minutes": 10,
                    "teacher_role": "Show contrasting ecosystem photos and elicit observations.",
                    "student_role": "Record observations and generate questions.",
                },
                {
                    "phase": "Explore",
                    "minutes": 20,
                    "teacher_role": "Facilitate case-study groups (deforestation, pollution, overfishing).",
                    "student_role": "Collect evidence on what changed and which species are affected.",
                },
                {
                    "phase": "Explain",
                    "minutes": 10,
                    "teacher_role": "Model cause-effect mapping and key vocabulary.",
                    "student_role": "Build a cause-effect map from their case.",
                },
                {
                    "phase": "Elaborate",
                    "minutes": 15,
                    "teacher_role": "Prompt evaluation of realistic interventions.",
                    "student_role": "Propose one solution justified with trade-offs.",
                },
                {
                    "phase": "Evaluate",
                    "minutes": 5,
                    "teacher_role": "Collect CER exit tickets.",
                    "student_role": "Submit claim, evidence, reasoning, and recommendation.",
                },
            ],
            "assessment": {
                "type": "CER_exit_ticket",
                "prompt": "Make a claim about the impact of your human activity, give two evidence points, explain reasoning, and recommend one solution.",
                "success_criteria": [
                    "Claim is clear",
                    "Evidence is accurate",
                    "Reasoning explains cause-effect",
                    "Solution includes trade-offs",
                ],
            },
            "differentiation": {
                "support": ["Provide CER sentence frames and simplified case summaries."],
                "extension": ["Compare two interventions and argue which is more feasible."],
            },
            "bloom_alignment": {
                "level": "Analyze → Evaluate",
                "note": "Students analyze relationships and evaluate solutions with evidence.",
            },
            "teacher_notes": [
                "Require evidence from the case study, not opinion alone.",
                "Discuss feasibility and unintended effects of solutions.",
            ],
        },
    },
    "formative_assessment": {
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "enum": ["english", "math", "science", "social_studies", "steam", "other"],
                    "title": "Subject",
                },
                "grade": {"type": "integer", "minimum": 0, "maximum": 12, "title": "Grade"},
                "topic": {"type": "string", "title": "Topic", "maxLength": 300},
                "assessment_type": {
                    "type": "string",
                    "enum": ["exit_ticket", "mini_quiz", "discussion_check"],
                    "title": "Assessment type",
                },
                "bloom_level": {
                    "type": "string",
                    "enum": ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"],
                    "title": "Bloom level",
                },
                "time_duration": {"type": "string", "title": "Time", "description": "e.g. 5 minutes"},
            },
            "required": ["subject", "grade", "topic", "assessment_type", "bloom_level", "time_duration"],
        },
        "exemplar_input": {
            "subject": "math",
            "grade": 6,
            "topic": "Ratios and equivalent ratios",
            "assessment_type": "exit_ticket",
            "bloom_level": "Apply",
            "time_duration": "5 minutes",
        },
        "exemplar_output": {
            "overview": "Five-minute exit ticket on writing and identifying equivalent ratios.",
            "learning_goals": [
                "Students write two equivalent ratios for a given situation.",
                "Students explain when two ratios are equivalent.",
            ],
            "materials": ["Exit slip or digital form"],
            "steps": [
                {
                    "title": "Administer exit ticket",
                    "description": "Students complete two questions independently in five minutes.",
                }
            ],
            "questions": [
                {
                    "question_text": "A recipe uses 2 cups of flour for every 3 cups of sugar. Write two equivalent ratios.",
                    "type": "short_answer",
                    "answer_key": "Accept 4:6, 6:9, or other correct equivalents.",
                    "difficulty": "medium",
                },
                {
                    "question_text": "How do you know two ratios are equivalent?",
                    "type": "short_answer",
                    "answer_key": "Same value when simplified or cross-multiplication equal.",
                    "difficulty": "medium",
                },
            ],
            "assessment": {
                "checks_for_understanding": [
                    "Scan for correct equivalent pairs.",
                    "Note common error: adding instead of scaling.",
                ],
                "rubric": None,
            },
            "teacher_notes": ["Use results to group students for the next lesson."],
        },
    },
    "english_task": {
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {"type": "integer", "minimum": 0, "maximum": 12, "title": "Grade"},
                "focus": {"type": "string", "enum": ["reading", "writing", "vocabulary"], "title": "Focus"},
                "topic": {"type": "string", "title": "Topic", "maxLength": 300},
                "learning_objective": {"type": "string", "title": "Learning objective", "maxLength": 400},
                "time_duration_minutes": {"type": "integer", "minimum": 5, "maximum": 120, "title": "Time (minutes)"},
                "bloom_level": {"type": "string", "title": "Bloom level"},
            },
            "required": ["grade", "focus", "topic", "learning_objective", "time_duration_minutes", "bloom_level"],
        },
        "exemplar_input": {
            "grade": 9,
            "focus": "reading",
            "topic": "Character change in a short story",
            "learning_objective": "Students explain how a character changes and support with two quotes.",
            "time_duration_minutes": 40,
            "bloom_level": "Analyze",
        },
        "exemplar_output": {
            "title": "Tracking Character Change With Evidence",
            "overview": "Students read a short excerpt and analyze how the main character changes from beginning to end.",
            "learning_objectives": [
                "Describe the character at the beginning and end.",
                "Support analysis with at least two accurate quotes.",
            ],
            "success_criteria": [
                "I can describe the character at the start and end.",
                "I include two accurate quotes with explanations.",
            ],
            "mini_lesson": {
                "teacher_model": "Think aloud: identify the character's trait at the start, a turning point, and the trait at the end.",
                "key_point": "Character change is shown through actions, dialogue, and consequences—not only stated feelings.",
            },
            "guided_practice": {
                "activity": "Annotate a shared paragraph for traits and evidence.",
                "teacher_prompts": [
                    "What does the character do that reveals their attitude?",
                    "Which quote best shows change?",
                ],
            },
            "independent_task": {
                "task": "Write a short paragraph explaining how the character changed using two quotes.",
                "expected_answer_format": "Claim + quote + explanation for each quote.",
            },
            "assessment": {
                "type": "written_response",
                "criteria": ["Accurate quotes", "Clear explanation of change", "Uses text evidence"],
            },
            "differentiation": {
                "support": ["Provide sentence frames and a two-column graphic organizer."],
                "extension": ["Compare the character's change to a second character in the text."],
            },
            "bloom_alignment": {
                "level": "Analyze",
                "note": "Students interpret character change using textual evidence.",
            },
            "teacher_notes": ["Model citing line numbers or phrases when quoting."],
        },
    },
    "engineering_activity": {
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {"type": "integer", "minimum": 0, "maximum": 12, "title": "Grade"},
                "topic": {"type": "string", "title": "Engineering topic", "maxLength": 300},
                "learning_objective": {"type": "string", "title": "Learning objective (optional)", "maxLength": 400},
                "time_duration_minutes": {"type": "integer", "minimum": 15, "maximum": 120, "title": "Time (minutes)"},
                "materials": {"type": "string", "title": "Materials available", "maxLength": 300},
                "constraints": {"type": "string", "title": "Constraints (optional)", "maxLength": 300},
                "bloom_level": {"type": "string", "title": "Bloom level"},
            },
            "required": ["grade", "topic", "time_duration_minutes", "bloom_level"],
        },
        "exemplar_input": {
            "grade": 8,
            "topic": "Structural stability and load distribution (truss bridges)",
            "learning_objective": "Students design, test, and improve a paper structure that spans 20 cm.",
            "time_duration_minutes": 45,
            "materials": "Paper, tape, scissors, coins",
            "constraints": "No hot glue; groups of 3",
            "bloom_level": "Create",
        },
        "exemplar_output": {
            "title": "Paper Truss Bridge Challenge",
            "concept_focus": "Forces, load distribution, and structural stability using triangle truss patterns.",
            "challenge_brief": "Build a paper bridge that spans 20 cm and holds the most coins before collapsing.",
            "success_criteria": [
                "Spans 20 cm without mid-span support",
                "Holds coins for 10 seconds",
                "Uses at least one triangle-based truss pattern",
            ],
            "materials": ["Paper", "Tape", "Scissors", "Coins"],
            "steps": [
                "Introduce two example truss patterns.",
                "Teams sketch two designs and choose one with justification.",
                "Build prototype (15 minutes).",
                "Test by adding coins one at a time; record maximum load.",
                "Change one variable and retest.",
            ],
            "assessment": {
                "type": "mini_rubric",
                "criteria": [
                    "Meets span and load constraints",
                    "Uses test data to justify design change",
                    "Explains why the change increased or decreased strength",
                ],
            },
            "differentiation": {
                "support": ["Provide a foldable truss template and assigned roles."],
                "extension": ["Calculate cost per coin held using a materials budget."],
            },
            "bloom_alignment": {
                "level": "Create",
                "note": "Students design, test, and iterate on an engineering solution.",
            },
            "teacher_notes": ["Emphasize safety with scissors and coin testing procedures."],
        },
    },
    "biodiversity_role_play": {
        "exemplar_input": {
            "grade_level": "Year 9",
            "issue": "Coastal development vs marine habitat protection",
            "roles": ["Developer", "Environmental scientist", "Local resident", "Government planner"],
            "bloom_level": "Evaluate",
            "format": "Structured debate",
        },
        "exemplar_output": {
            "background_brief": "A coastal town is considering a new marina expansion. The project promises jobs and tourism revenue but may affect seagrass beds and fish nursery habitats.",
            "role_assignment_sheets": [
                {
                    "role": "Developer",
                    "stakeholder_goals": "Secure project approval and highlight economic benefits.",
                    "key_arguments": ["Job creation", "Tourism growth", "Tax revenue"],
                    "data_references": ["Regional employment statistics", "Projected visitor numbers"],
                },
                {
                    "role": "Environmental scientist",
                    "stakeholder_goals": "Protect biodiversity and ecosystem services.",
                    "key_arguments": ["Habitat loss", "Species decline", "Water quality risk"],
                    "data_references": ["Marine survey reports", "IUCN species status summaries"],
                },
                {
                    "role": "Local resident",
                    "stakeholder_goals": "Balance livelihoods, access to the coast, and quality of life.",
                    "key_arguments": ["Fishing livelihoods", "Recreation access", "Noise and traffic"],
                    "data_references": ["Community survey highlights"],
                },
                {
                    "role": "Government planner",
                    "stakeholder_goals": "Propose regulated development with mitigation measures.",
                    "key_arguments": ["Zoning options", "Environmental offsets", "Monitoring requirements"],
                    "data_references": ["Existing coastal regulations", "Environmental impact assessment guidelines"],
                },
            ],
            "debate_structure": [
                "Opening statements (2 minutes per role)",
                "Rebuttal round",
                "Evidence round with cited data",
                "Closing statements and policy vote",
            ],
            "reflection_prompts": [
                "Which trade-off was hardest to resolve?",
                "What policy would best balance economics and ecology?",
            ],
            "assessment": {
                "criteria": [
                    "Uses evidence to support claims",
                    "Acknowledges trade-offs ethically",
                    "Participates respectfully in structured debate",
                ]
            },
        },
    },
    "parent_communication": {
        "exemplar_input": {
            "audience": "parents",
            "tone": "friendly",
            "topic": "Upcoming science fair and family support",
            "grade": 7,
        },
        "exemplar_output": {
            "overview": "Family communication for Grade 7 upcoming science fair.",
            "learning_goals": [
                "Inform families about date, time, and location.",
                "Clarify how students should prepare displays.",
            ],
            "materials": ["Optional link to science fair rubric"],
            "steps": [
                {
                    "title": "Send message",
                    "description": "Share the communication below via email or school portal.",
                }
            ],
            "communication": {
                "subject_line": "Grade 7 Science Fair — Thursday, March 14",
                "message_body": (
                    "Dear families,\n\nOur Grade 7 students will showcase inquiry projects at the science fair on "
                    "Thursday, March 14 from 3:30–5:00 p.m. in the gymnasium. Students should bring a completed "
                    "display board and be ready to explain their question, method, and findings.\n\nThank you for "
                    "supporting their curiosity and hard work."
                ),
                "key_details": [
                    "Date: Thursday, March 14",
                    "Time: 3:30–5:00 p.m.",
                    "Location: School gymnasium",
                    "Students bring display board and lab notebook",
                ],
                "call_to_action": "Please RSVP by March 7 if you can attend or volunteer at the welcome table.",
            },
            "teacher_notes": ["Offer translation support if needed for multilingual families."],
        },
    },
    "concept_quest_adventure": {
        "input_schema": {
            "type": "object",
            "properties": {
                "grade_level": {"type": "string", "title": "Grade level", "description": "e.g. Grade 6"},
                "subject": {
                    "type": "string",
                    "title": "Subject",
                    "enum": ["science", "history", "geography", "literature", "economics", "other"],
                },
                "topic": {"type": "string", "title": "Topic", "maxLength": 200},
                "bloom_level": {"type": "string", "title": "Bloom level"},
                "game_duration": {"type": "string", "title": "Duration", "description": "e.g. 30 minutes"},
                "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"], "title": "Difficulty"},
                "team_mode": {"type": "boolean", "title": "Team mode"},
            },
            "required": ["grade_level", "subject", "topic", "bloom_level", "game_duration", "difficulty", "team_mode"],
        },
        "exemplar_input": {
            "grade_level": "Grade 6",
            "subject": "science",
            "topic": "Food chains and energy transfer",
            "bloom_level": "Apply",
            "game_duration": "30 minutes",
            "difficulty": "Medium",
            "team_mode": True,
        },
        "exemplar_output": {
            "title": "The Food Chain Quest",
            "story_scenario": "The class enters an ecosystem where energy flow has been disrupted. Teams must complete missions to restore balance before the system collapses.",
            "mission_levels": [
                {
                    "level_title": "Level 1 — Identify Key Concepts",
                    "description": "Sort organisms into producers, consumers, and decomposers.",
                    "student_task": "Classify cards correctly and defend one choice.",
                },
                {
                    "level_title": "Level 2 — Build the Food Web",
                    "description": "Connect organisms into a working food web.",
                    "student_task": "Arrange cards to show energy flow arrows.",
                },
                {
                    "level_title": "Level 3 — Disruption Challenge",
                    "description": "Predict effects when one species is removed.",
                    "student_task": "Explain two impacts using cause-effect reasoning.",
                },
            ],
            "game_mechanics": [
                "Teams earn quest points for correct classifications.",
                "Bonus points for clear scientific explanations.",
                "Timed mini-challenges between levels.",
            ],
            "assessment": [
                {"skill": "Concept recognition", "evidence": "Correctly classifies organisms and relationships."},
                {"skill": "Systems thinking", "evidence": "Predicts effects when one organism is removed."},
                {"skill": "Scientific reasoning", "evidence": "Uses vocabulary accurately in explanations."},
            ],
            "teacher_facilitation": [
                "Form teams and explain the story hook.",
                "Distribute cards and mission instructions.",
                "Facilitate each level with quick debriefs.",
                "Close with a reflection on energy transfer.",
            ],
        },
    },
    "field_investigation_planner": {
        "exemplar_input": {
            "grade_level": "Year 7",
            "ecosystem_type": "Wetland",
            "investigation_focus": "Water quality and biodiversity",
            "tools_available": ["Thermometer", "pH strips", "Clipboards"],
            "bloom_level": "Analyze",
            "risk_level": "Low",
        },
        "exemplar_output": {
            "fieldwork_objective": "Students measure abiotic factors and record biodiversity indicators to assess wetland health.",
            "step_by_step_protocol": [
                "Review safety boundaries and low-risk handling of equipment.",
                "Measure water temperature at three sample points.",
                "Test pH at each point and record on the data table.",
                "Record visible species and habitat observations.",
                "Return to class and clean equipment.",
            ],
            "data_collection_table": {
                "headers": ["Sample point", "Temperature (°C)", "pH", "Observations"],
                "description": "Students record one row per sample point during the wetland visit.",
            },
            "data_analysis_prompts": [
                "What patterns do you notice across sample points?",
                "Does pH suggest possible stress on the ecosystem? Use evidence.",
            ],
            "reflection_systems_link": "How might upstream land use affect this wetland system over time?",
        },
    },
    "gis_mapping_spatial_analysis": {
        "exemplar_input": {
            "grade_level": "Year 10",
            "map_layers": ["Population density", "Transportation networks", "Economic activity"],
            "region": "South-East Asia",
            "learning_objective": "Students analyze how infrastructure influences economic development.",
            "bloom_level": "Analyze",
            "assessment_type": "Spatial analysis report",
        },
        "exemplar_output": {
            "activity_overview": "Students analyze how population, transport, and economic layers interact to explain development patterns in South-East Asia.",
            "map_layer_analysis": [
                "Identify clusters of high population density.",
                "Trace major transport corridors linking cities.",
                "Locate economic activity centers and ports.",
            ],
            "spatial_pattern_questions": [
                "Where do economic centers cluster relative to coastlines and transport routes?",
                "How might limited transport access affect rural development?",
            ],
            "comparative_task": "Compare two cities in the region and explain geographic advantages using map evidence.",
            "student_output": "Write a 400–500 word spatial analysis report with labeled map references.",
            "assessment_rubric": [
                {
                    "criteria": "Spatial interpretation",
                    "description": "Identifies and describes patterns using map layers accurately.",
                },
                {
                    "criteria": "Geographic reasoning",
                    "description": "Explains relationships between infrastructure and development.",
                },
                {
                    "criteria": "Evidence use",
                    "description": "Supports claims with specific map-based evidence.",
                },
            ],
            "bloom_alignment": {
                "level": "Analyze",
                "description": "Students analyze spatial relationships and justify conclusions with map evidence.",
            },
        },
    },
    "global_geography_strategy": {
        "exemplar_input": {
            "grade_level": "Year 9",
            "subject": "Geography",
            "topic": "Climate change and resource management",
            "bloom_level": "Evaluate",
            "game_duration": "50 minutes",
            "regions": ["Asia", "Europe", "Africa", "Americas"],
        },
        "exemplar_output": {
            "title": "Planet Earth Strategy Game",
            "scenario": "Student teams represent world regions managing resources while responding to climate-related challenges.",
            "game_rounds": [
                {
                    "round_title": "Energy Production",
                    "description": "Teams choose an energy strategy for their region.",
                    "choices": ["Expand renewables", "Mixed energy plan", "Continue fossil reliance"],
                },
                {
                    "round_title": "Economic Development",
                    "description": "Teams invest in development priorities.",
                    "choices": ["Infrastructure", "Education", "Healthcare"],
                },
                {
                    "round_title": "Climate Disaster",
                    "description": "A regional climate event requires emergency resource allocation.",
                    "choices": ["Share aid globally", "Protect domestic resources", "Negotiate trade for aid"],
                },
            ],
            "game_mechanics": [
                "Track economy score after each round.",
                "Track environmental health score.",
                "Track global cooperation score.",
            ],
            "assessment": [
                {"skill": "Geographical understanding", "evidence": "Justifies resource decisions using regional needs."},
                {"skill": "Systems thinking", "evidence": "Explains long-term effects of round choices."},
                {"skill": "Ethical reasoning", "evidence": "Balances sustainability with development goals."},
            ],
        },
    },
}


def apply_exemplar_batch_patches(templates: List[Dict[str, Any]]) -> None:
    """Merge batch patches into template seed data by slug."""
    by_slug = {item["template"]["slug"]: item for item in templates}
    for slug, patch in EXEMPLAR_BATCH_PATCHES.items():
        item = by_slug.get(slug)
        if not item:
            continue
        version = item["version"]
        if "input_schema" in patch:
            version["input_schema"] = deepcopy(patch["input_schema"])
        prompt = version.setdefault("prompt_definition", {})
        if "description" in patch:
            prompt["description"] = patch["description"]
        if "context" in patch:
            prompt["context"] = patch["context"]
        if "exemplar_input" in patch:
            prompt["exemplar_input"] = deepcopy(patch["exemplar_input"])
        if "exemplar_output" in patch:
            prompt["exemplar_output"] = deepcopy(patch["exemplar_output"])
