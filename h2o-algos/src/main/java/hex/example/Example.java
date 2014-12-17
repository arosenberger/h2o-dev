package hex.example;

import hex.Model;
import hex.SupervisedModelBuilder;
import hex.schemas.ExampleV2;
import hex.schemas.ModelBuilderSchema;
import water.H2O.H2OCountedCompleter;
import water.MRTask;
import water.Scope;
import water.fvec.Chunk;
import water.util.Log;

import java.util.Arrays;

/**
 *  Example model builder... building a trivial ExampleModel
 */
public class Example extends SupervisedModelBuilder<ExampleModel,ExampleModel.ExampleParameters,ExampleModel.ExampleOutput> {
  @Override
  public Model.ModelCategory[] can_build() {
    return new Model.ModelCategory[]{
            Model.ModelCategory.Unknown,
    };
  }

  // Called from Nano thread; start the Example Job on a F/J thread
  public Example( ExampleModel.ExampleParameters parms ) { super("Example",parms); init(false); }

  public ModelBuilderSchema schema() { return new ExampleV2(); }

  @Override public Example trainModel() {
    return (Example)start(new ExampleDriver(), _parms._max_iters);
  }

  /** Initialize the ModelBuilder, validating all arguments and preparing the
   *  training frame.  This call is expected to be overridden in the subclasses
   *  and each subclass will start with "super.init();".  This call is made
   *  by the front-end whenever the GUI is clicked, and needs to be fast;
   *  heavy-weight prep needs to wait for the trainModel() call.
   *
   *  Validate the max_iters. */
  @Override public void init(boolean expensive) {
    super.init(expensive);
    if( _parms._max_iters < 1 || _parms._max_iters > 9999999 )
      error("max_iters", "must be between 1 and 10 million");
  }

  // ----------------------
  @Override protected void trainModel() {
    try(Model model = new ExampleModel(this)) {
      // Run the main Example Loop; Stop after enough iterations
      for( ; model._output._iters < _parms._max_iters && isRunning(); model._output._iters++ ) {

        // Do the Math; collect results
        model._output._maxs = new Max().doAll(_parms.train())._maxs;

        // Atomically update the Model to the world
        progressed();           // One unit of work
        model.update();         // Update model in K/V store
      }
    }
  }


  // -------------------------------------------------------------------------
  // Find max per-column
  private static class Max extends MRTask<Max> {
    // IN

    // OUT
    double[] _maxs;

    @Override public void map(Chunk[] cs) {
      _maxs = new double[cs.length];
      Arrays.fill(_maxs,-Double.MAX_VALUE);
      for( int col = 0; col < cs.length; col++ )
        for( int row = 0; row < cs[col]._len; row++ )
          _maxs[col] = Math.max(_maxs[col],cs[col].at0(row));
    }

    @Override public void reduce(Max that) {
      for( int col = 0; col < _maxs.length; col++ )
        _maxs[col] = Math.max(_maxs[col],that._maxs[col]);
    }
  }
}
