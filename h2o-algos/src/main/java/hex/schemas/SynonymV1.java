package hex.schemas;

import water.Iced;
import water.api.API;
import water.api.KeyV1.ModelKeyV1;
import water.api.Schema;

public class SynonymV1 extends Schema<Iced, SynonymV1> {

  // Input fields
  @API(help="A word2vec model key.") public ModelKeyV1 key;
  @API(help="The target string to find synonyms.") public String target;
  @API(help="Find the top `cnt` synonyms of the target word.") public int cnt;


  //Outputs
  @API(help="The synonyms.", direction=API.Direction.OUTPUT) public String[] synonyms;
  @API(help="The cosine similarities.", direction=API.Direction.OUTPUT) public float[]  cos_sim;

/*  @Override public SynonymsHandler.Synonyms fillImpl(Synonyms c) {
    //c._w2vec_key = Key.make(key);
    c._cnt = cnt;
    c._target = target;
    return c;
  }
  */
}
