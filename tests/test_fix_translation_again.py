
import pandas as pd
import os
import sys

# Add the project root to sys.path to import core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.asr_backend.audio_preprocess import save_results
from core._4_2_translate import split_chunks_by_chars
from core.translate_lines import translate_lines

def test_audio_preprocess_cleaning():
    print("Testing audio_preprocess cleaning...")
    # Mock data with hallucinations
    data = {
        'text': ['hello', ' ', '梁', '梁梁梁梁', 'world', '', '' * 10],
        'start': [0, 1, 2, 2, 3, 4, 4],
        'end': [1, 1, 2.1, 2, 4, 4, 4],
        'speaker_id': ['A'] * 7
    }
    df = pd.DataFrame(data)
    
    # We need to mock _2_CLEANED_CHUNKS to point to a test file
    test_output = 'output/log/test_cleaned_chunks.xlsx'
    import core.asr_backend.audio_preprocess
    core.asr_backend.audio_preprocess._2_CLEANED_CHUNKS = test_output
    
    save_results(df)
    
    df_cleaned = pd.read_excel(test_output)
    print("Cleaned text:", df_cleaned['text'].tolist())
    
    remaining = [t.strip('"') for t in df_cleaned['text'].tolist()]
    assert 'hello' in remaining
    assert 'world' in remaining
    assert '梁梁梁梁' not in remaining
    assert ' ' not in remaining
    assert '' not in remaining
    print("✅ audio_preprocess cleaning test passed!")

def test_chunking_logic():
    print("Testing chunking logic...")
    # Mock _3_2_SPLIT_BY_MEANING
    test_file = 'output/log/test_split_by_meaning.txt'
    with open(test_file, 'w') as f:
        f.write("Line 1\n\nLine 2\n\n\nLine 3")
    
    import core._4_2_translate
    core._4_2_translate._3_2_SPLIT_BY_MEANING = test_file
    
    chunks = split_chunks_by_chars(chunk_size=100, max_i=10)
    print("Chunks:", chunks)
    assert "" not in chunks
    assert all(c.strip() for c in chunks)
    print("✅ chunking logic test passed!")

def test_translate_lines_robustness():
    print("Testing translate_lines robustness...")
    res1, res2 = translate_lines("", None, None, None, None)
    assert res1 == "" and res2 == ""
    
    res1, res2 = translate_lines("   \n  ", None, None, None, None)
    assert res1 == "" and res2 == ""
    print("✅ translate_lines robustness test passed!")

if __name__ == "__main__":
    os.makedirs('output/log', exist_ok=True)
    try:
        test_audio_preprocess_cleaning()
        test_chunking_logic()
        test_translate_lines_robustness()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
