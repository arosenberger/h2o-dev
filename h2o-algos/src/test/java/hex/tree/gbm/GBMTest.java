package hex.tree.gbm;

import hex.ConfusionMatrix;
import hex.tree.gbm.GBMModel.GBMParameters.Family;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import water.*;
import water.fvec.Chunk;
import water.fvec.Frame;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class GBMTest extends TestUtil {

  @BeforeClass public static void stall() { stall_till_cloudsize(1); }

  private abstract class PrepData { abstract int prep(Frame fr); }

  static final String ignored_aircols[] = new String[] { "DepTime", "ArrTime", "AirTime", "ArrDelay", "DepDelay", "TaxiIn", "TaxiOut", "Cancelled", "CancellationCode", "Diverted", "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay", "IsDepDelayed"};

  @Test public void testGBMRegression() {
    GBMModel gbm = null;
    Frame fr = null, fr2 = null;
    try {
      fr = parse_test_file("./smalldata/gbm_test/Mfgdata_gaussian_GBM_testing.csv");
      GBMModel.GBMParameters parms = new GBMModel.GBMParameters();
      parms._train = fr._key;
      parms._loss = Family.AUTO;
      parms._convert_to_enum = false;     // Regression
      parms._response_column = fr._names[1]; // Row in col 0, dependent in col 1, predictor in col 2
      parms._ntrees = 1;
      parms._max_depth = 1;
      parms._min_rows = 1;
      parms._nbins = 20;
      // Drop ColV2 0 (row), keep 1 (response), keep col 2 (only predictor), drop remaining cols
      String[] xcols = parms._ignored_columns = new String[fr.numCols()-2];
      xcols[0] = fr._names[0];
      System.arraycopy(fr._names,3,xcols,1,fr.numCols()-3);
      parms._learn_rate = 1.0f;
      parms._score_each_iteration=true;

      GBM job = null;
      try {
        job = new GBM(parms);
        gbm = job.trainModel().get();
      } finally {
        if (job != null) job.remove();
      }
      Assert.assertTrue(job._state == water.Job.JobState.DONE); //HEX-1817
      //Assert.assertTrue(gbm._output._state == Job.JobState.DONE); //HEX-1817

      // Done building model; produce a score column with predictions
      fr2 = gbm.score(fr);
      double sq_err = new CompErr().doAll(job.response(),fr2.vecs()[0])._sum;
      double mse = sq_err/fr2.numRows();
      assertEquals(79152.1233,mse,0.1);
      assertEquals(79152.1233,gbm._output._mse_train[1],0.1);

    } finally {
      if( fr  != null ) fr .remove();
      if( fr2 != null ) fr2.remove();
      if( gbm != null ) gbm.delete();
    }
  }

  private static class CompErr extends MRTask<CompErr> {
    double _sum;
    @Override public void map( Chunk resp, Chunk pred ) {
      double sum = 0;
      for( int i=0; i<resp._len; i++ ) {
        double err = resp.at0(i)-pred.at0(i);
        sum += err*err;
      }
      _sum = sum;
    }
    @Override public void reduce( CompErr ce ) { _sum += ce._sum; }
  }

  @Test public void testBasicGBM() {
    // Regression tests
    basicGBM("./smalldata/junit/cars.csv",
             new PrepData() { int prep(Frame fr ) {fr.remove("name").remove(); return ~fr.find("economy (mpg)"); }});
    
    // Classification tests
    basicGBM("./smalldata/junit/test_tree.csv",
             new PrepData() { int prep(Frame fr) { return 1; }
             });
    basicGBM("./smalldata/junit/test_tree_minmax.csv",
             new PrepData() { int prep(Frame fr) { return fr.find("response"); }
             });
    basicGBM("./smalldata/logreg/prostate.csv",
             new PrepData() { int prep(Frame fr) { fr.remove("ID").remove(); return fr.find("CAPSULE"); }
             });
    basicGBM("./smalldata/junit/cars.csv",
             new PrepData() { int prep(Frame fr) { fr.remove("name").remove(); return fr.find("cylinders"); }
             });
    basicGBM("./smalldata/airlines/allyears2k_headers.zip",
             new PrepData() { int prep(Frame fr) {
               for( String s : ignored_aircols ) fr.remove(s).remove();
               return fr.find("IsArrDelayed"); }
             });
//    // Bigger Tests
//    basicGBM("../datasets/98LRN.CSV",
//             new PrepData() { int prep(Frame fr ) {
//               fr.remove("CONTROLN").remove(); 
//               fr.remove("TARGET_D").remove(); 
//               return fr.find("TARGET_B"); }});

//    basicGBM("../datasets/UCI/UCI-large/covtype/covtype.data",
//             new PrepData() { int prep(Frame fr) { return fr.numCols()-1; } });
  }

  @Test public void testBasicGBMFamily() {
    Scope.enter();
    // Classification with Bernoulli family
    basicGBM("./smalldata/logreg/prostate.csv",
             new PrepData() {
               int prep(Frame fr) {
                 fr.remove("ID").remove(); // Remove not-predictive ID
                 int ci = fr.find("RACE"); // Change RACE to categorical
                 Scope.track(fr.replace(ci,fr.vecs()[ci].toEnum())._key);
                 return fr.find("CAPSULE"); // Prostate: predict on CAPSULE
               }
             }, false, Family.bernoulli);
    Scope.exit();
  }

  // ==========================================================================
  public void basicGBM(String fname, PrepData prep) {
    basicGBM(fname, prep, false, Family.AUTO);
  }
  public GBMModel.GBMOutput basicGBM(String fname, PrepData prep, boolean validation, Family family) {
    GBMModel gbm = null;
    Frame fr = null, fr2= null, vfr=null;
    try {
      Scope.enter();
      fr = parse_test_file(fname);
      int idx = prep.prep(fr); // hack frame per-test
      DKV.put(fr);             // Update frame after hacking it

      GBMModel.GBMParameters parms = new GBMModel.GBMParameters();
      if( idx < 0 ) { parms._convert_to_enum = false; idx = ~idx; } else { parms._convert_to_enum = true; }
      parms._train = fr._key;
      parms._response_column = fr._names[idx];
      parms._ntrees = 4;
      parms._loss = family;
      parms._max_depth = 4;
      parms._min_rows = 1;
      parms._nbins = 50;
      parms._learn_rate = .2f;
      parms._score_each_iteration=true;
      if( validation ) {        // Make a validation frame thats a clone of the training data
        vfr = new Frame(fr);
        DKV.put(vfr);
        parms._valid = vfr._key;
      }

      GBM job = null;
      try {
        job = new GBM(parms);
        gbm = job.trainModel().get();
      } finally {
        if( job != null ) job.remove();
      }

      // Done building model; produce a score column with predictions
      fr2 = gbm.score(fr);

      Assert.assertTrue(job._state == water.Job.JobState.DONE); //HEX-1817
      //Assert.assertTrue(gbm._output._state == Job.JobState.DONE); //HEX-1817
      return gbm._output;

    } finally {
      if( fr  != null ) fr .remove();
      if( fr2 != null ) fr2.remove();
      if( vfr != null ) vfr.remove();
      if( gbm != null ) gbm.delete();
      Scope.exit();
    }
  }

  // Test-on-Train.  Slow test, needed to build a good model.
  @Test public void testGBMTrainTest() {
    GBMModel gbm = null;
    GBMModel.GBMParameters parms = new GBMModel.GBMParameters();
    try {
      parms._valid = parse_test_file("smalldata/gbm_test/ecology_eval.csv" )._key;
      Frame  train = parse_test_file("smalldata/gbm_test/ecology_model.csv");
      train.remove("Site").remove();     // Remove unique ID
      DKV.put(train);                    // Update frame after hacking it
      parms._train = train._key;
      parms._response_column = "Angaus"; // Train on the outcome
      parms._convert_to_enum = true;
      parms._ntrees = 5;
      parms._max_depth = 10;
      parms._min_rows = 10;
      parms._nbins = 100;
      parms._learn_rate = .2f;
      parms._loss = Family.AUTO;

      GBM job = null;
      try {
        job = new GBM(parms);
        gbm = job.trainModel().get();
      } finally {
        if( job != null ) job.remove();
      }

      hex.ModelMetrics mm = hex.ModelMetrics.getFromDKV(gbm,parms.valid());

      double auc = mm._aucdata.AUC();
      Assert.assertTrue(0.80 <= auc && auc < 0.83); // Sanely good model
      ConfusionMatrix cmf1 = mm._aucdata.CM();
      Assert.assertArrayEquals(ar(ar(311,82),ar(32,75)),cmf1._arr);

    } finally {
      parms._train.remove();
      parms._valid.remove();
      if( gbm != null ) gbm.delete();
    }
  }

  // Adapt a trained model to a test dataset with different enums
  @Test public void testModelAdapt() {
    GBM job = null;
    GBMModel gbm = null;
    GBMModel.GBMParameters parms = new GBMModel.GBMParameters();
    try {
      Scope.enter();
      Frame v;
      parms._train = (  parse_test_file("smalldata/junit/mixcat_train.csv"))._key;
      parms._valid = (v=parse_test_file("smalldata/junit/mixcat_test.csv" ))._key;
      parms._response_column = "Response"; // Train on the outcome
      parms._ntrees = 1; // Build a CART tree - 1 tree, full learn rate, down to 1 row
      parms._learn_rate = 1.0f;
      parms._min_rows = 1;
      parms._loss = Family.AUTO;

      job = new GBM(parms);
      gbm = job.trainModel().get();

      Frame res = gbm.score(v);

      int[] ps = new int[(int)v.numRows()];
      for( int i=0; i<ps.length; i++ ) ps[i] = (int)res.vecs()[0].at8(i);
      // Expected predictions are X,X,Y,Y,X,Y,Z,X,Y
      // Never predicts W, the extra class in the test set.
      // Badly predicts Z because 1 tree does not pick up that feature#2 can also
      // be used to predict Z, and instead relies on factor C which does not appear
      // in the test set.
      Assert.assertArrayEquals("",ps,new int[]{1,1,2,2,1,2,3,1,2});

      res.remove();

    } finally {
      parms._train.remove();
      parms._valid.remove();
      if( gbm != null ) gbm.delete();
      if( job != null ) job.remove();
      Scope.exit();
    }
  }

  // A test of locking the input dataset during model building.
  @Test public void testModelLock() {
    GBM gbm=null;
    Frame fr=null;
    try {
      GBMModel.GBMParameters parms = new GBMModel.GBMParameters();
      fr = parse_test_file("smalldata/gbm_test/ecology_model.csv");
      fr.remove("Site").remove();        // Remove unique ID
      DKV.put(fr);                       // Update after hacking
      parms._train = fr._key;
      parms._response_column = "Angaus"; // Train on the outcome
      parms._ntrees = 10;
      parms._max_depth = 10;
      parms._min_rows = 1;
      parms._nbins = 20;
      parms._learn_rate = .2f;
      gbm = new GBM(parms);
      gbm.trainModel();
      try { Thread.sleep(50); } catch( Exception ignore ) { }

      try {
        fr.delete();            // Attempted delete while model-build is active
        Assert.fail("Should toss IAE instead of reaching here");
      } catch( IllegalArgumentException ignore ) {
      } catch( DException.DistributedException de ) {
        assertTrue( de.getMessage().contains("java.lang.IllegalArgumentException") );
      }

      GBMModel model = gbm.get();
      Assert.assertTrue(gbm._state == Job.JobState.DONE); //HEX-1817
      if( model != null ) model.delete();

    } finally {
      if( fr  != null ) fr .remove();
      if( gbm != null ) gbm.remove();             // Remove GBM Job
    }
  }

  //  MSE generated by GBM with/without validation dataset should be same
  @Test public void testModelMSEEqualityOnProstate() {
    final PrepData prostatePrep = new PrepData() { @Override int prep(Frame fr) { fr.remove("ID").remove(); return fr.find("CAPSULE"); } };
    double[] mseWithoutVal = basicGBM("./smalldata/logreg/prostate.csv", prostatePrep, false, Family.AUTO)._mse_train;
    double[] mseWithVal    = basicGBM("./smalldata/logreg/prostate.csv", prostatePrep, true , Family.AUTO)._mse_valid;
    Assert.assertArrayEquals("GBM has to report same list of MSEs for run without/with validation dataset (which is equal to training data)", mseWithoutVal, mseWithVal, 0.0001);
  }

  @Test public void testModelMSEEqualityOnTitanic() {
    final PrepData titanicPrep = new PrepData() { @Override int prep(Frame fr) { return fr.find("survived"); } };
    double[] mseWithoutVal = basicGBM("./smalldata/junit/titanic_alt.csv", titanicPrep, false, Family.AUTO)._mse_train;
    double[] mseWithVal    = basicGBM("./smalldata/junit/titanic_alt.csv", titanicPrep, true , Family.AUTO)._mse_valid;
    Assert.assertArrayEquals("GBM has to report same list of MSEs for run without/with validation dataset (which is equal to training data)", mseWithoutVal, mseWithVal, 0.0001);
  }

}
