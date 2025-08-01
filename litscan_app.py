import streamlit as st
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pandas as pd
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("Plotly not available. Charts will be disabled.")
from anthropic import Anthropic
import time
import re

# Drug database from uploaded Excel file
DRUG_DATABASE = [
    "ABRILADA", "ACETAMINOPHEN, DEXTROMETHORPHAN HBr", "ACETAMINOPHEN, DEXTROMETHORPHAN HBr, PHENYLEPHRINE HCl",
    "ACETAMINOPHEN, DEXTROMETHORPHAN, PHENYLEPHRINE", "ACETAMINOPHEN, DIPHENHYDRAMINE HCL, PHENYLEPHRINE HCL",
    "ACULAR LS", "ACUVAIL", "ACZONE", "ADMELOG", "ALOCRIL", "ALPHAGAN P", "AMG 193", "ANTIVENIN", 
    "ARTHROTEC", "ATAZANAVIR", "AZACTAM", "AZTREONAM", "Acarbose", "Acetaminophen", "Advair", "Advil",
    "Amlodipine", "Amoxicillin", "Aspirin", "Atorvastatin", "Azithromycin", "Benadryl", "Celebrex",
    "Crestor", "Cymbalta", "Diovan", "Enbrel", "Fosamax", "Humira", "Humulin", "Ibuprofen", "Insulin",
    "Keytruda", "Lantus", "Lasix", "Lexapro", "Lipitor", "Lisinopril", "Lyrica", "Metformin", "Nexium",
    "Norvasc", "OxyContin", "Ozempic", "Plavix", "Pradaxa", "Prednisone", "Prilosec", "Prozac",
    "Repatha", "Rituxan", "Rybelsus", "Singulair", "Synthroid", "Trulicity", "Tylenol", "Vasotec",
    "Viagra", "Vioxx", "Warfarin", "Xarelto", "Zantac", "Zepbound", "Zocor", "Zoloft", "Zyprexa",
    "adalimumab", "alemtuzumab", "bevacizumab", "cetuximab", "daratumumab", "evolocumab", "infliximab",
    "ipilimumab", "natalizumab", "nivolumab", "obinutuzumab", "ofatumumab", "panitumumab", "pembrolizumab",
    "pertuzumab", "ramucirumab", "rituximab", "secukinumab", "tocilizumab", "trastuzumab", "ustekinumab",
    "vedolizumab", "tirzepatide", "semaglutide", "dulaglutide", "liraglutide", "exenatide", "insulin human",
    "insulin aspart", "insulin glargine", "insulin detemir", "insulin lispro", "metformin", "sitagliptin",
    "empagliflozin", "canagliflozin", "dapagliflozin", "ertugliflozin", "alogliptin", "linagliptin",
    "saxagliptin", "vildagliptin", "acarbose", "miglitol", "nateglinide", "repaglinide", "rosiglitazone",
    "pioglitazone", "glipizide", "glyburide", "glimepiride", "chlorpropamide", "tolbutamide", "tolazamide"
]

def filter_drug_suggestions(query, drug_list=DRUG_DATABASE, max_suggestions=10):
    """Filter drug database based on user input"""
    if not query:
        return []
    
    query_lower = query.lower()
    suggestions = []
    
    # Exact matches first
    for drug in drug_list:
        if drug.lower() == query_lower:
            suggestions.append(drug)
    
    # Starts with matches
    for drug in drug_list:
        if drug.lower().startswith(query_lower) and drug not in suggestions:
            suggestions.append(drug)
    
    # Contains matches
    for drug in drug_list:
        if query_lower in drug.lower() and drug not in suggestions:
            suggestions.append(drug)
    
    return suggestions[:max_suggestions]
st.set_page_config(
    page_title="PaperSafe AI - Your safety net for scientific literature",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
        margin: 1rem 0;
    }
    .safety-signal-high {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .safety-signal-medium {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .safety-signal-low {
        background-color: #e8f5e8;
        border-left: 4px solid #4caf50;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .paper-summary {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border: 1px solid #dee2e6;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables"""
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'safety_signals' not in st.session_state:
        st.session_state.safety_signals = []

def search_pubmed(compound_name, max_results=20, therapeutic_area=None):
    """Search PubMed for papers related to the compound using official E-utilities API"""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    # Enhanced search query with safety-related terms and therapeutic area
    safety_terms = [
        "adverse event", "side effect", "toxicity", "safety", "pharmacovigilance", 
        "drug interaction", "contraindication", "warning", "precaution", "risk"
    ]
    
    # Build comprehensive search query
    compound_query = f'("{compound_name}"[Title/Abstract] OR "{compound_name}"[MeSH Terms])'
    safety_query = " OR ".join([f'"{term}"[Title/Abstract]' for term in safety_terms])
    
    # Add therapeutic area if specified
    area_query = ""
    if therapeutic_area and therapeutic_area != "Other":
        area_terms = {
            "Oncology": ["cancer", "tumor", "oncology", "chemotherapy", "neoplasm"],
            "Cardiovascular": ["cardiovascular", "cardiac", "heart", "hypertension", "cholesterol"],
            "Neuroscience": ["neurological", "brain", "nervous system", "alzheimer", "parkinson"],
            "Immunology": ["immunology", "autoimmune", "inflammation", "arthritis"],
            "Metabolic": ["diabetes", "metabolic", "obesity", "glucose", "insulin"]
        }
        if therapeutic_area in area_terms:
            area_query = " AND (" + " OR ".join([f'"{term}"[Title/Abstract]' for term in area_terms[therapeutic_area]]) + ")"
    
    search_query = f'({compound_query}) AND ({safety_query}){area_query}'
    
    try:
        st.info(f"🔍 Searching PubMed for: {compound_name}")
        st.caption(f"Search query: {search_query[:100]}...")
        
        # Search for paper IDs
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            'db': 'pubmed',
            'term': search_query,
            'retmax': max_results,
            'retmode': 'xml',
            'sort': 'pub+date',
            'datetype': 'pdat',
            'reldate': '1825'  # Last 5 years
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=30)
        search_response.raise_for_status()
        
        search_root = ET.fromstring(search_response.content)
        
        # Check for errors
        error_elem = search_root.find('.//ErrorList')
        if error_elem is not None:
            st.warning(f"PubMed search warning: {error_elem.text}")
        
        # Extract PMIDs
        pmids = [id_elem.text for id_elem in search_root.findall('.//Id')]
        
        if not pmids:
            st.warning(f"No papers found for '{compound_name}' with safety-related terms. Try a different compound name.")
            return []
        
        st.success(f"✅ Found {len(pmids)} papers. Retrieving details...")
        
        # Fetch paper details in batches to avoid timeouts
        papers = []
        batch_size = 10
        
        for i in range(0, len(pmids), batch_size):
            batch_pmids = pmids[i:i+batch_size]
            
            fetch_url = f"{base_url}efetch.fcgi"
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(batch_pmids),
                'retmode': 'xml',
                'rettype': 'abstract'
            }
            
            fetch_response = requests.get(fetch_url, params=fetch_params, timeout=30)
            fetch_response.raise_for_status()
            
            fetch_root = ET.fromstring(fetch_response.content)
            
            for article in fetch_root.findall('.//PubmedArticle'):
                try:
                    # Extract article information with better error handling
                    title_elem = article.find('.//ArticleTitle')
                    title = title_elem.text if title_elem is not None else "No title available"
                    
                    # Handle multiple abstract sections
                    abstract_texts = []
                    for abstract_elem in article.findall('.//AbstractText'):
                        if abstract_elem.text:
                            label = abstract_elem.get('Label', '')
                            text = abstract_elem.text
                            if label:
                                abstract_texts.append(f"{label}: {text}")
                            else:
                                abstract_texts.append(text)
                    
                    abstract = " ".join(abstract_texts) if abstract_texts else "No abstract available"
                    
                    # Extract authors with affiliations
                    authors = []
                    for author in article.findall('.//Author'):
                        lastname = author.find('.//LastName')
                        forename = author.find('.//ForeName')
                        if lastname is not None and forename is not None:
                            authors.append(f"{forename.text} {lastname.text}")
                    
                    # Extract comprehensive publication date
                    pub_date = "Unknown"
                    pub_year = article.find('.//PubDate/Year')
                    pub_month = article.find('.//PubDate/Month')
                    
                    if pub_year is not None:
                        if pub_month is not None:
                            pub_date = f"{pub_month.text} {pub_year.text}"
                        else:
                            pub_date = pub_year.text
                    
                    # Extract PMID
                    pmid_elem = article.find('.//PMID')
                    pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
                    
                    # Extract journal information
                    journal_elem = article.find('.//Journal/Title')
                    journal = journal_elem.text if journal_elem is not None else "Unknown Journal"
                    
                    # Extract DOI if available
                    doi_elem = article.find('.//ArticleId[@IdType="doi"]')
                    doi = doi_elem.text if doi_elem is not None else None
                    
                    papers.append({
                        'pmid': pmid,
                        'title': title,
                        'abstract': abstract,
                        'authors': ', '.join(authors[:3]) + (' et al.' if len(authors) > 3 else ''),
                        'pub_date': pub_date,
                        'journal': journal,
                        'doi': doi,
                        'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        'compound_mentioned': compound_name.lower() in (title + " " + abstract).lower()
                    })
                    
                except Exception as e:
                    st.warning(f"Error parsing article {pmid}: {str(e)}")
                    continue
        
        st.success(f"✅ Successfully retrieved {len(papers)} papers from PubMed")
        return papers
        
    except requests.exceptions.Timeout:
        st.error("⏰ PubMed search timed out. Please try again with fewer papers or check your internet connection.")
        return []
    except requests.exceptions.RequestException as e:
        st.error(f"🌐 Network error accessing PubMed: {str(e)}")
        return []
    except ET.ParseError as e:
        st.error(f"📄 Error parsing PubMed response: {str(e)}")
        return []
    except Exception as e:
        st.error(f"❌ Unexpected error searching PubMed: {str(e)}")
        return []

def analyze_with_claude(paper, compound_name, anthropic_client):
    """Analyze a paper using Claude AI with structured risk assessment"""
    try:
        st.write(f"🤖 Analyzing: {paper['title'][:50]}...")  # Debug info
        
        prompt = f"""
        You are a senior drug safety scientist analyzing scientific literature for pharmaceutical regulatory compliance.
        
        Analyze this research paper about the compound "{compound_name}" and provide a structured safety assessment.
        
        Title: {paper['title']}
        Abstract: {paper['abstract']}
        
        CRITICAL: I need you to identify and count specific safety signals. Please be thorough and specific.
        
        Please provide your analysis in EXACTLY this format:
        
        ADVERSE_EVENTS_COUNT: [number]
        ADVERSE_EVENTS_LIST:
        - [list each specific adverse event mentioned, one per line]
        
        DRUG_INTERACTIONS_COUNT: [number]
        DRUG_INTERACTIONS_LIST:
        - [list each specific drug interaction mentioned, one per line]
        
        CONTRAINDICATIONS_COUNT: [number]
        CONTRAINDICATIONS_LIST:
        - [list each specific contraindication mentioned, one per line]
        
        SAFETY_SIGNALS_DETECTED:
        - [any other safety concerns not covered above]
        
        KEY_FINDINGS:
        - [summarize the main safety-related findings in 2-3 bullet points]
        
        REGULATORY_IMPACT:
        - [assess if this requires 15-day FDA reporting or other regulatory action]
        
        SAFETY_DOMAINS:
        - [categorize into: Hepatic, Cardiac, Neurological, Gastrointestinal, Dermatological, Renal, Hematological, Other]
        
        CLINICAL_SIGNIFICANCE:
        - [brief assessment of clinical relevance and patient impact]
        
        IMPORTANT: 
        - Count EVERY adverse event, drug interaction, and contraindication mentioned
        - Be specific and thorough in your counting
        - Include mild, moderate, and severe events
        - Don't miss any safety signals
        """
        
        # Debug API call
        st.write("🔗 Making API call to Claude...")
        
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Updated to latest model
            max_tokens=1500,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        st.write("✅ Received response from Claude")  # Debug info
        
        return response_text
        
    except Exception as e:
        error_msg = f"Claude API Error: {str(e)}"
        st.error(error_msg)
        st.write(f"Error details: {type(e).__name__}")
        
        # Return a fallback analysis
        return f"""
        ADVERSE_EVENTS_COUNT: 0
        ADVERSE_EVENTS_LIST:
        - Analysis failed due to API error
        
        DRUG_INTERACTIONS_COUNT: 0
        DRUG_INTERACTIONS_LIST:
        - Analysis failed due to API error
        
        CONTRAINDICATIONS_COUNT: 0
        CONTRAINDICATIONS_LIST:
        - Analysis failed due to API error
        
        SAFETY_SIGNALS_DETECTED:
        - API Error: {error_msg}
        
        KEY_FINDINGS:
        - Unable to analyze due to API connection issue
        
        REGULATORY_IMPACT:
        - Analysis incomplete due to technical error
        
        SAFETY_DOMAINS:
        - Other
        
        CLINICAL_SIGNIFICANCE:
        - Analysis could not be completed
        """

def calculate_risk_level(analysis_text):
    """Calculate risk level based on systematic scoring of safety signals"""
    try:
        # Extract counts from Claude's analysis
        ae_count = 0
        interaction_count = 0
        contraindication_count = 0
        
        # Extract adverse events count
        ae_match = re.search(r'ADVERSE_EVENTS_COUNT:\s*(\d+)', analysis_text, re.IGNORECASE)
        if ae_match:
            ae_count = int(ae_match.group(1))
        
        # Extract drug interactions count
        interaction_match = re.search(r'DRUG_INTERACTIONS_COUNT:\s*(\d+)', analysis_text, re.IGNORECASE)
        if interaction_match:
            interaction_count = int(interaction_match.group(1))
        
        # Extract contraindications count
        contraindication_match = re.search(r'CONTRAINDICATIONS_COUNT:\s*(\d+)', analysis_text, re.IGNORECASE)
        if contraindication_match:
            contraindication_count = int(contraindication_match.group(1))
        
        # Calculate risk score
        total_safety_signals = ae_count + interaction_count + contraindication_count
        
        # Risk assessment logic
        if total_safety_signals >= 5 or contraindication_count >= 2 or interaction_count >= 3:
            risk_level = "HIGH"
            risk_rationale = f"High risk: {ae_count} adverse events, {interaction_count} drug interactions, {contraindication_count} contraindications"
        elif total_safety_signals >= 2 or contraindication_count >= 1 or interaction_count >= 1:
            risk_level = "MEDIUM"
            risk_rationale = f"Medium risk: {ae_count} adverse events, {interaction_count} drug interactions, {contraindication_count} contraindications"
        elif total_safety_signals > 0:
            risk_level = "LOW"
            risk_rationale = f"Low risk: {ae_count} adverse events, {interaction_count} drug interactions, {contraindication_count} contraindications"
        else:
            risk_level = "LOW"
            risk_rationale = "No specific safety signals identified"
        
        # Check for serious adverse events in text (additional risk factors)
        serious_ae_keywords = [
            "death", "fatal", "mortality", "life-threatening", "hospitalization", 
            "serious adverse event", "severe", "toxicity", "black box warning",
            "discontinuation", "withdrawal", "contraindicated"
        ]
        
        serious_count = sum(1 for keyword in serious_ae_keywords 
                          if keyword.lower() in analysis_text.lower())
        
        # Upgrade risk if serious events mentioned
        if serious_count >= 3 and risk_level != "HIGH":
            risk_level = "HIGH"
            risk_rationale += f" (upgraded due to {serious_count} serious safety terms)"
        elif serious_count >= 1 and risk_level == "LOW":
            risk_level = "MEDIUM"
            risk_rationale += f" (upgraded due to {serious_count} serious safety terms)"
        
        return {
            'risk_level': risk_level,
            'risk_rationale': risk_rationale,
            'adverse_events_count': ae_count,
            'drug_interactions_count': interaction_count,
            'contraindications_count': contraindication_count,
            'total_safety_signals': total_safety_signals,
            'serious_terms_count': serious_count
        }
        
    except Exception as e:
        return {
            'risk_level': 'UNKNOWN',
            'risk_rationale': f'Error calculating risk: {str(e)}',
            'adverse_events_count': 0,
            'drug_interactions_count': 0,
            'contraindications_count': 0,
            'total_safety_signals': 0,
            'serious_terms_count': 0
        }

def parse_claude_analysis(analysis_text):
    """Parse Claude's analysis into structured data with enhanced risk assessment"""
    try:
        # Calculate systematic risk level
        risk_data = calculate_risk_level(analysis_text)
        
        # Extract adverse events list
        ae_section = re.search(r'ADVERSE_EVENTS_LIST:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        adverse_events = []
        if ae_section:
            ae_lines = ae_section.group(1).strip().split('\n')
            adverse_events = [line.strip('- ').strip() for line in ae_lines if line.strip().startswith('-')]
        
        # Extract drug interactions list
        interaction_section = re.search(r'DRUG_INTERACTIONS_LIST:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        drug_interactions = []
        if interaction_section:
            interaction_lines = interaction_section.group(1).strip().split('\n')
            drug_interactions = [line.strip('- ').strip() for line in interaction_lines if line.strip().startswith('-')]
        
        # Extract contraindications list
        contraindication_section = re.search(r'CONTRAINDICATIONS_LIST:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        contraindications = []
        if contraindication_section:
            contraindication_lines = contraindication_section.group(1).strip().split('\n')
            contraindications = [line.strip('- ').strip() for line in contraindication_lines if line.strip().startswith('-')]
        
        # Extract other safety signals
        signals_section = re.search(r'SAFETY_SIGNALS_DETECTED:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        other_signals = []
        if signals_section:
            signal_lines = signals_section.group(1).strip().split('\n')
            other_signals = [line.strip('- ').strip() for line in signal_lines if line.strip().startswith('-')]
        
        # Extract key findings
        findings_section = re.search(r'KEY_FINDINGS:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        findings = []
        if findings_section:
            finding_lines = findings_section.group(1).strip().split('\n')
            findings = [line.strip('- ').strip() for line in finding_lines if line.strip().startswith('-')]
        
        # Extract regulatory impact
        regulatory_section = re.search(r'REGULATORY_IMPACT:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        regulatory_impact = regulatory_section.group(1).strip() if regulatory_section else "No specific regulatory action identified"
        
        # Extract safety domains
        domains_section = re.search(r'SAFETY_DOMAINS:(.*?)(?=\n[A-Z_]+:|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        domains = []
        if domains_section:
            domain_lines = domains_section.group(1).strip().split('\n')
            domains = [line.strip('- ').strip() for line in domain_lines if line.strip().startswith('-')]
        
        # Combine all safety signals for display
        all_safety_signals = adverse_events + drug_interactions + contraindications + other_signals
        
        return {
            'risk_level': risk_data['risk_level'],
            'risk_rationale': risk_data['risk_rationale'],
            'adverse_events_count': risk_data['adverse_events_count'],
            'drug_interactions_count': risk_data['drug_interactions_count'],
            'contraindications_count': risk_data['contraindications_count'],
            'total_safety_signals': risk_data['total_safety_signals'],
            'serious_terms_count': risk_data['serious_terms_count'],
            'adverse_events': adverse_events,
            'drug_interactions': drug_interactions,
            'contraindications': contraindications,
            'safety_signals': all_safety_signals,  # Combined list for backwards compatibility
            'other_signals': other_signals,
            'key_findings': findings,
            'regulatory_impact': regulatory_impact,
            'safety_domains': domains,
            'full_analysis': analysis_text
        }
        
    except Exception as e:
        return {
            'risk_level': 'UNKNOWN',
            'risk_rationale': 'Analysis parsing error',
            'adverse_events_count': 0,
            'drug_interactions_count': 0,
            'contraindications_count': 0,
            'total_safety_signals': 0,
            'serious_terms_count': 0,
            'adverse_events': [],
            'drug_interactions': [],
            'contraindications': [],
            'safety_signals': [],
            'other_signals': [],
            'key_findings': [],
            'regulatory_impact': 'Analysis parsing error',
            'safety_domains': [],
            'full_analysis': analysis_text
        }

def create_safety_dashboard(analyzed_papers):
    """Create safety signal dashboard"""
    if not analyzed_papers:
        return
    
    # Count risk levels
    risk_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'UNKNOWN': 0}
    domain_counts = {}
    all_signals = []
    
    for paper in analyzed_papers:
        analysis = paper.get('analysis', {})
        risk_level = analysis.get('risk_level', 'UNKNOWN')
        risk_counts[risk_level] += 1
        
        # Count safety domains
        domains = analysis.get('safety_domains', [])
        for domain in domains:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        # Collect all safety signals
        signals = analysis.get('safety_signals', [])
        all_signals.extend(signals)
    
    # Create visualizations
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Risk Level Distribution")
        risk_df = pd.DataFrame(list(risk_counts.items()), columns=['Risk Level', 'Count'])
        risk_df = risk_df[risk_df['Count'] > 0]
        
        if PLOTLY_AVAILABLE and len(risk_df) > 0:
            colors = {'HIGH': '#f44336', 'MEDIUM': '#ff9800', 'LOW': '#4caf50', 'UNKNOWN': '#9e9e9e'}
            color_sequence = [colors.get(level, '#9e9e9e') for level in risk_df['Risk Level']]
            
            fig_risk = px.pie(risk_df, values='Count', names='Risk Level', 
                             color_discrete_sequence=color_sequence,
                             title="Safety Risk Assessment")
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            # Fallback to simple text display if Plotly not available
            st.markdown("**Risk Level Summary:**")
            for level, count in risk_counts.items():
                if count > 0:
                    color = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢', 'UNKNOWN': '⚪'}
                    st.markdown(f"{color.get(level, '⚪')} **{level}**: {count} papers")
    
    with col2:
        st.subheader("Safety Domains Affected")
        if domain_counts:
            # Create a clean list format instead of bar chart
            st.markdown("**Papers by Safety Domain:**")
            
            # Sort domains by count (highest first)
            sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
            
            for domain, count in sorted_domains:
                # Create clean domain display with count
                domain_clean = domain.strip()
                if domain_clean:
                    # Use different colors based on count
                    if count >= 3:
                        color = "#dc3545"  # Red for high
                        icon = "🔴"
                    elif count >= 2:
                        color = "#fd7e14"  # Orange for medium
                        icon = "🟡"
                    else:
                        color = "#28a745"  # Green for low
                        icon = "🟢"
                    
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; margin: 0.3rem 0; background-color: #f8f9fa; border-radius: 5px; border-left: 3px solid {color};">
                        <span style="color: #495057;"><strong>{domain_clean}</strong></span>
                        <span style="color: {color}; font-weight: bold;">{icon} {count} paper{'s' if count != 1 else ''}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No safety domains identified in analyzed papers")

def main():
    initialize_session_state()
    
    # Header
    st.markdown('<h1 class="main-header">🛡️ PaperSafe AI - Your safety net for scientific literature</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666; font-size: 1.1rem; margin-top: -1rem;">By Ty Root</p>', unsafe_allow_html=True)
    
    # Show current analysis status
    if st.session_state.analysis_complete and st.session_state.search_results:
        compound_analyzed = st.session_state.search_results[0].get('compound_mentioned', 'Unknown compound')
        st.success(f"📊 Currently showing analysis for: **{compound_name if 'compound_name' in locals() else 'Previous search'}** | {len(st.session_state.search_results)} papers analyzed")
    else:
        st.markdown("""
        <div style='text-align: center; margin: 2rem 0;'>
            <h3 style='color: #1f77b4; margin-bottom: 1rem;'>Transforming pharmaceutical drug safety monitoring through AI-powered literature analysis</h3>
            <p style='font-size: 1.1rem; color: #666; margin-bottom: 0.5rem;'>Reducing literature review time from 20+ hours to <4 hours per week</p>
            <p style='font-size: 1.1rem; color: #666; margin-bottom: 0.5rem;'>Automated FDA compliance monitoring | AI-powered safety signal detection</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("🎯 Search Parameters")
        
        # API Key input (back to manual entry for security)
        api_key = st.text_input(
            "Claude API Key", 
            type="password",
            help="Enter your Anthropic Claude API key (required for AI analysis)",
            placeholder="sk-ant-api03-..."
        )
        
        # Drug input options
        input_method = st.radio(
            "Input Method",
            ["Type compound name", "Select from database"],
            horizontal=True,
            help="Choose how to enter the drug compound"
        )
        
        if input_method == "Type compound name":
            # Initialize compound name in session state if not exists
            if 'compound_input' not in st.session_state:
                st.session_state.compound_input = "AMG 193"
            
            compound_name = st.text_input(
                "Drug Compound Name",
                value=st.session_state.compound_input,
                help="Enter the compound name (e.g., AMG 193, Repatha, Humira, etc.)",
                placeholder="Start typing a drug name...",
                key="compound_text_input"
            )
            
            # Update session state when text changes
            if compound_name != st.session_state.compound_input:
                st.session_state.compound_input = compound_name
            
            # Show autocomplete suggestions if user is typing
            if compound_name and len(compound_name.strip()) >= 2:
                suggestions = filter_drug_suggestions(compound_name.strip())
                
                # Only show suggestions if the current input is not already a perfect match
                if suggestions and compound_name.strip() not in [s.strip() for s in suggestions[:3]]:
                    st.markdown("**💡 Suggestions:**")
                    
                    # Display suggestions in a more compact way
                    for i, suggestion in enumerate(suggestions[:6]):  # Show up to 6 suggestions
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"🔹 **{suggestion}**")
                        with col2:
                            if st.button("Use", key=f"use_suggestion_{i}_{suggestion}", help=f"Use {suggestion}"):
                                st.session_state.compound_input = suggestion
                                st.rerun()
        
        else:  # Select from database
            compound_name = st.selectbox(
                "Select Drug Compound",
                options=[""] + sorted(DRUG_DATABASE),
                index=0,
                help="Choose from our database of common pharmaceutical compounds",
                key="compound_selectbox"
            )
        
        therapeutic_area = st.selectbox(
            "Therapeutic Area",
            ["Oncology", "Cardiovascular", "Neuroscience", "Immunology", "Metabolic", "Other"]
        )
        
        max_papers = st.slider(
            "Maximum Papers to Analyze",
            min_value=5,
            max_value=50,
            value=15,
            help="Number of recent papers to retrieve and analyze"
        )
        
        # Search and Clear buttons with matching styling
        search_button = st.button("🔍 Search & Analyze Literature", type="primary", use_container_width=True)
        clear_button = st.button("🗑️ Clear Results or Stop Scan", type="secondary", use_container_width=True)
        
        # Handle clear button
        if clear_button:
            # Clear all session state
            st.session_state.search_results = []
            st.session_state.analysis_complete = False
            st.session_state.safety_signals = []
            st.success("✅ Results cleared! Ready for new search.")
            st.rerun()
        
        st.markdown("---")
        st.markdown("**About PaperSafe AI**")
        st.markdown("Your safety net for scientific literature")
        st.markdown("Reduces review time from 20+ hours to <4 hours per week")
        st.markdown("Automated FDA compliance monitoring")
        st.markdown("AI-powered safety signal detection")
        
        # Show current session status
        if st.session_state.analysis_complete:
            st.markdown("---")
            st.markdown("**Current Session:**")
            st.success(f"✅ {len(st.session_state.search_results)} papers analyzed")
            st.caption("Use 'Clear Results' to start fresh")
    
    # Main content area
    if search_button:
        if not api_key:
            st.error("⚠️ Please enter your Claude API key in the sidebar to enable AI analysis")
            st.info("💡 Get your API key from: https://console.anthropic.com/")
            return
        
        if not compound_name:
            st.error("⚠️ Please enter a compound name")
            return
        
        # Initialize Claude client
        try:
            st.write("🔑 Initializing Claude API client...")  # Debug info
            anthropic_client = Anthropic(api_key=api_key)
            
            # Test API connection with a simple call
            st.write("🧪 Testing API connection...")
            test_message = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": "Hello, respond with 'API connection successful'"}]
            )
            
            if "successful" in test_message.content[0].text.lower():
                st.write("✅ Claude API connection verified")
            else:
                st.warning("⚠️ Unusual API response, but connection seems to work")
                
        except Exception as e:
            st.error(f"❌ Error with Claude API: {str(e)}")
            st.error("Common issues:")
            st.error("• API key format should be: sk-ant-api03-...")
            st.error("• Check if you have sufficient API credits")
            st.error("• Verify API key is active at https://console.anthropic.com/")
            return
        
        # Progress tracking
        progress_container = st.container()
        with progress_container:
            st.info(f"🔍 Searching PubMed for papers related to '{compound_name}'...")
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        # Search PubMed
        papers = search_pubmed(compound_name, max_papers, therapeutic_area)
        
        if not papers:
            st.warning(f"No papers found for compound '{compound_name}'. Try a different compound name or search terms.")
            return
        
        progress_bar.progress(25)
        status_text.text(f"Found {len(papers)} papers. Starting AI analysis...")
        
        # Analyze papers with Claude
        analyzed_papers = []
        total_papers = len(papers)
        
        for i, paper in enumerate(papers):
            progress_percentage = 25 + int((i / total_papers) * 70)
            progress_bar.progress(progress_percentage)
            status_text.text(f"Analyzing paper {i+1}/{total_papers}: {paper['title'][:50]}...")
            
            analysis_text = analyze_with_claude(paper, compound_name, anthropic_client)
            analysis_data = parse_claude_analysis(analysis_text)
            
            paper['analysis'] = analysis_data
            analyzed_papers.append(paper)
            
            # Small delay to prevent API rate limiting
            time.sleep(0.5)
        
        progress_bar.progress(100)
        status_text.text("✅ Analysis complete!")
        
        # Store results in session state
        st.session_state.search_results = analyzed_papers
        st.session_state.analysis_complete = True
        
        # Clear progress indicators
        progress_container.empty()
    
    # Display results if analysis is complete
    if st.session_state.analysis_complete and st.session_state.search_results:
        analyzed_papers = st.session_state.search_results
        
        # Executive Summary
        st.header("📊 Executive Safety Summary")
        
        # Key metrics with enhanced risk details
        col1, col2, col3, col4 = st.columns(4)
        
        high_risk_count = sum(1 for p in analyzed_papers if p.get('analysis', {}).get('risk_level') == 'HIGH')
        medium_risk_count = sum(1 for p in analyzed_papers if p.get('analysis', {}).get('risk_level') == 'MEDIUM')
        total_papers = len(analyzed_papers)
        
        # Calculate total safety signals across all papers
        total_adverse_events = sum(p.get('analysis', {}).get('adverse_events_count', 0) for p in analyzed_papers)
        total_interactions = sum(p.get('analysis', {}).get('drug_interactions_count', 0) for p in analyzed_papers)
        total_contraindications = sum(p.get('analysis', {}).get('contraindications_count', 0) for p in analyzed_papers)
        
        # Count papers requiring FDA reporting (based on high risk or specific regulatory mentions)
        fda_reporting_count = sum(1 for p in analyzed_papers 
                                 if p.get('analysis', {}).get('risk_level') == 'HIGH' 
                                 or 'fda' in p.get('analysis', {}).get('regulatory_impact', '').lower() 
                                 or 'reporting' in p.get('analysis', {}).get('regulatory_impact', '').lower())
        
        with col1:
            st.metric("Total Papers Analyzed", total_papers)
        with col2:
            st.metric("High Risk Signals", high_risk_count, 
                     delta=f"{high_risk_count/total_papers*100:.1f}%" if total_papers > 0 else "0%")
        with col3:
            st.metric("Medium Risk Signals", medium_risk_count, 
                     delta=f"{medium_risk_count/total_papers*100:.1f}%" if total_papers > 0 else "0%")
        with col4:
            st.metric("FDA Reporting Required", fda_reporting_count)
        
        # Additional safety metrics row
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("Total Adverse Events", total_adverse_events)
        with col6:
            st.metric("Drug Interactions", total_interactions)
        with col7:
            st.metric("Contraindications", total_contraindications)
        with col8:
            total_safety_signals = total_adverse_events + total_interactions + total_contraindications
            st.metric("Total Safety Signals", total_safety_signals)
        
        # Safety Dashboard
        st.header("📈 Safety Signal Dashboard")
        create_safety_dashboard(analyzed_papers)
        
        # Detailed Paper Analysis
        st.header("📋 Detailed Paper Analysis")
        
        # Filter options
        risk_filter = st.selectbox(
            "Filter by Risk Level",
            ["All", "HIGH", "MEDIUM", "LOW"],
            key="risk_filter"
        )
        
        # Filter papers based on selection
        filtered_papers = analyzed_papers
        if risk_filter != "All":
            filtered_papers = [p for p in analyzed_papers 
                             if p.get('analysis', {}).get('risk_level') == risk_filter]
        
        # Display filtered papers
        for i, paper in enumerate(filtered_papers):
            analysis = paper.get('analysis', {})
            risk_level = analysis.get('risk_level', 'UNKNOWN')
            
            # Choose styling based on risk level
            if risk_level == 'HIGH':
                card_class = "safety-signal-high"
                risk_color = "🔴"
            elif risk_level == 'MEDIUM':
                card_class = "safety-signal-medium"
                risk_color = "🟡"
            elif risk_level == 'LOW':
                card_class = "safety-signal-low"
                risk_color = "🟢"
            else:
                card_class = "safety-signal-low"
                risk_color = "⚪"
            
            with st.expander(f"{risk_color} {paper['title'][:100]}... - Risk: {risk_level}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"**Authors:** {paper['authors']}")
                    st.markdown(f"**Publication Date:** {paper['pub_date']}")
                    st.markdown(f"**PMID:** [{paper['pmid']}]({paper['url']})")
                    
                    st.markdown("**Abstract:**")
                    st.markdown(paper['abstract'][:500] + "..." if len(paper['abstract']) > 500 else paper['abstract'])
                
                with col2:
                    st.markdown(f"**Risk Level:** {risk_color} {risk_level}")
                    
                    # Show detailed risk breakdown
                    if analysis.get('risk_rationale'):
                        st.markdown("**Risk Assessment:**")
                        st.caption(analysis['risk_rationale'])
                    
                    # Safety signal counts
                    ae_count = analysis.get('adverse_events_count', 0)
                    interaction_count = analysis.get('drug_interactions_count', 0)
                    contraindication_count = analysis.get('contraindications_count', 0)
                    
                    if ae_count > 0 or interaction_count > 0 or contraindication_count > 0:
                        st.markdown("**Safety Signal Counts:**")
                        if ae_count > 0:
                            st.markdown(f"• **{ae_count}** Adverse Events")
                        if interaction_count > 0:
                            st.markdown(f"• **{interaction_count}** Drug Interactions")
                        if contraindication_count > 0:
                            st.markdown(f"• **{contraindication_count}** Contraindications")
                    
                    # Show specific adverse events if available
                    if analysis.get('adverse_events') and len(analysis['adverse_events']) > 0:
                        st.markdown("**Adverse Events:**")
                        for event in analysis['adverse_events'][:3]:  # Show first 3
                            if event.strip():
                                st.markdown(f"• {event}")
                    
                    # Show drug interactions if available
                    if analysis.get('drug_interactions') and len(analysis['drug_interactions']) > 0:
                        st.markdown("**Drug Interactions:**")
                        for interaction in analysis['drug_interactions'][:2]:  # Show first 2
                            if interaction.strip():
                                st.markdown(f"• {interaction}")
                    
                    # Show contraindications if available
                    if analysis.get('contraindications') and len(analysis['contraindications']) > 0:
                        st.markdown("**Contraindications:**")
                        for contraindication in analysis['contraindications'][:2]:  # Show first 2
                            if contraindication.strip():
                                st.markdown(f"• {contraindication}")
                    
                    # Show safety domains
                    if analysis.get('safety_domains'):
                        st.markdown("**Safety Domains:**")
                        for domain in analysis['safety_domains'][:3]:  # Show first 3
                            if domain.strip():
                                st.markdown(f"• {domain}")
                
                # Full analysis details
                with st.expander("View Full AI Analysis & Risk Calculation"):
                    # Risk calculation details
                    st.markdown("### 🎯 Risk Assessment Details")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("Adverse Events", analysis.get('adverse_events_count', 0))
                    with col_b:
                        st.metric("Drug Interactions", analysis.get('drug_interactions_count', 0))
                    with col_c:
                        st.metric("Contraindications", analysis.get('contraindications_count', 0))
                    
                    st.markdown(f"**Risk Rationale:** {analysis.get('risk_rationale', 'Not available')}")
                    
                    # Show all identified safety signals
                    if analysis.get('adverse_events'):
                        st.markdown("**All Adverse Events Identified:**")
                        for i, event in enumerate(analysis['adverse_events'], 1):
                            if event.strip():
                                st.markdown(f"{i}. {event}")
                    
                    if analysis.get('drug_interactions'):
                        st.markdown("**All Drug Interactions Identified:**")
                        for i, interaction in enumerate(analysis['drug_interactions'], 1):
                            if interaction.strip():
                                st.markdown(f"{i}. {interaction}")
                    
                    if analysis.get('contraindications'):
                        st.markdown("**All Contraindications Identified:**")
                        for i, contraindication in enumerate(analysis['contraindications'], 1):
                            if contraindication.strip():
                                st.markdown(f"{i}. {contraindication}")
                    
                    st.markdown("### 📋 Key Findings")
                    for finding in analysis.get('key_findings', []):
                        if finding.strip():
                            st.markdown(f"• {finding}")
                    
                    st.markdown("### 🏛️ Regulatory Impact")
                    st.markdown(analysis.get('regulatory_impact', 'Not specified'))
                    
                    st.markdown("### 🤖 Complete AI Analysis")
                    with st.expander("Show Raw Analysis Text"):
                        st.text(analysis.get('full_analysis', 'No analysis available'))
        
        # Export functionality
        st.header("📤 Export Results")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Create summary report
            if st.button("📄 Generate Executive Report"):
                report_data = {
                    'compound': compound_name,
                    'analysis_date': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'total_papers': len(analyzed_papers),
                    'high_risk': high_risk_count,
                    'medium_risk': medium_risk_count,
                    'fda_reporting': fda_reporting_count
                }
                
                st.success("Executive report generated!")
                st.json(report_data)
        
        with col2:
            # Download data as CSV
            if st.button("💾 Download CSV Data"):
                # Prepare data for CSV
                csv_data = []
                for paper in analyzed_papers:
                    analysis = paper.get('analysis', {})
                    csv_data.append({
                        'PMID': paper['pmid'],
                        'Title': paper['title'],
                        'Authors': paper['authors'],
                        'Publication_Date': paper['pub_date'],
                        'Risk_Level': analysis.get('risk_level', ''),
                        'Safety_Signals': '; '.join(analysis.get('safety_signals', [])),
                        'Safety_Domains': '; '.join(analysis.get('safety_domains', [])),
                        'Regulatory_Impact': analysis.get('regulatory_impact', ''),
                        'URL': paper['url']
                    })
                
                df = pd.DataFrame(csv_data)
                csv = df.to_csv(index=False)
                
                st.download_button(
                    label="Download Analysis Results",
                    data=csv,
                    file_name=f"litscan_analysis_{compound_name}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p><strong>PaperSafe AI</strong> - Your safety net for scientific literature</p>
        <p>Reducing literature review time from 20+ hours to <4 hours per week | Automated FDA compliance | AI-powered safety detection</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
