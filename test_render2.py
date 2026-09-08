with open('tests/test_color_fit.py', 'r') as f:
    content = f.read()

# Let's verify why failing_render.calls is not incremented...
# Because `_verify_candidate` runs TWICE! One for candidate and one for the output!
# wait, how many times does `render` get called?
# Source 1 page -> `_build_candidate` calls `render` (call 1)
# `_verify_candidate(candidate_path)` calls `render` (call 2)
# `_verify_candidate(output_path)` calls `render` (call 3)

# BUT wait! Does it raise RuntimeError? YES, but `fit_color_vector_pdf` might catch it and return a status?
# No, look at `fit_color_vector_pdf`:
#    except Exception:
#        if output_created:
#            output_path.unlink(missing_ok=True)
#        raise

# So it should raise! But maybe the regex didn't match? Let me check `src/pdf_size_fit/color_fit.py`.
