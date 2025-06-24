#!/usr/bin/env python3
"""Test runner for ComfyUI Docker Project tests"""

import argparse
from io import StringIO
import pathlib
import sys
import unittest


def discover_and_run_tests(
    test_dir: pathlib.Path,
    pattern: str = "test_*.py",
    verbosity: int = 2,
    failfast: bool = False,
) -> bool:
    """
    Discover and run all tests in the given directory.

    Args:
        test_dir: Directory containing test files
        pattern: Pattern to match test files
        verbosity: Test output verbosity (0=quiet, 1=normal, 2=verbose)
        failfast: Stop on first failure

    Returns:
        True if all tests passed, False otherwise
    """
    # Add the project root to Python path so imports work
    project_root = test_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Discover tests
    loader = unittest.TestLoader()
    start_dir = str(test_dir)
    suite = loader.discover(start_dir, pattern=pattern)

    # Run tests
    stream = StringIO()
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=verbosity,
        failfast=failfast,
        buffer=True,  # Capture stdout/stderr during tests
    )

    print(f"Running tests from {test_dir} (pattern: {pattern})")
    print("=" * 70)

    result = runner.run(suite)

    # Print results
    output = stream.getvalue()
    print(output)

    # Summary
    tests_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)

    print("\n" + "=" * 70)
    print("Test Summary:")
    print(f"  Tests run: {tests_run}")
    print(f"  Failures: {failures}")
    print(f"  Errors: {errors}")
    print(f"  Skipped: {skipped}")

    if failures > 0:
        print(f"\nFAILURES ({failures}):")
        for test, traceback in result.failures:
            print(
                f"  - {test}: {traceback.split()[-1] if traceback else 'Unknown failure'}"
            )

    if errors > 0:
        print(f"\nERRORS ({errors}):")
        for test, traceback in result.errors:
            print(
                f"  - {test}: {traceback.split()[-1] if traceback else 'Unknown error'}"
            )

    if skipped > 0:
        print(f"\nSKIPPED ({skipped}):")
        for test, reason in result.skipped:
            print(f"  - {test}: {reason}")

    success = failures == 0 and errors == 0
    if success:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ {failures + errors} test(s) failed!")

    return success


def check_dependencies():
    """Check if required test dependencies are available."""
    missing_deps = []

    try:
        import yaml
    except ImportError:
        missing_deps.append("PyYAML")

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    if missing_deps:
        print("Warning: Some dependencies are missing:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nSome tests may be skipped. Install missing dependencies with:")
        print(f"  pip install {' '.join(missing_deps)}")
        print()

    return len(missing_deps) == 0


def run_specific_test(
    test_dir: pathlib.Path, test_name: str, verbosity: int = 2
) -> bool:
    """Run a specific test module or test case."""
    # Add the project root to Python path
    project_root = test_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Try to load the specific test
    loader = unittest.TestLoader()

    try:
        if "." in test_name:
            # Specific test method (e.g., test_validate_config.TestClass.test_method)
            suite = loader.loadTestsFromName(test_name)
        else:
            # Test module (e.g., test_validate_config)
            if not test_name.startswith("test_"):
                test_name = f"test_{test_name}"
            suite = loader.loadTestsFromName(test_name)
    except (ImportError, AttributeError) as e:
        print(f"Error loading test '{test_name}': {e}")
        return False

    # Run the specific test
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return len(result.failures) == 0 and len(result.errors) == 0


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests for ComfyUI Docker Project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_runner.py                    # Run all tests
  python test_runner.py --test validate   # Run validation tests only
  python test_runner.py --pattern "*yaml*" # Run YAML-related tests only
  python test_runner.py --quiet           # Run with minimal output
  python test_runner.py --failfast        # Stop on first failure
        """,
    )

    parser.add_argument("--test", "-t", help="Run specific test module or test case")
    parser.add_argument(
        "--pattern",
        "-p",
        default="test_*.py",
        help="Pattern to match test files (default: test_*.py)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output (same as --verbosity 2)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet output (same as --verbosity 0)",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        help="Test output verbosity (0=quiet, 1=normal, 2=verbose)",
    )
    parser.add_argument(
        "--failfast", "-f", action="store_true", help="Stop on first failure"
    )
    parser.add_argument(
        "--no-deps-check", action="store_true", help="Skip dependency check"
    )

    args = parser.parse_args()

    # Determine verbosity
    if args.verbosity is not None:
        verbosity = args.verbosity
    elif args.verbose:
        verbosity = 2
    elif args.quiet:
        verbosity = 0
    else:
        verbosity = 1

    # Find test directory
    test_dir = pathlib.Path(__file__).parent
    if not test_dir.exists():
        print(f"Error: Test directory {test_dir} not found")
        return 1

    # Check dependencies unless skipped
    if not args.no_deps_check:
        check_dependencies()

    # Run tests
    try:
        if args.test:
            success = run_specific_test(test_dir, args.test, verbosity)
        else:
            success = discover_and_run_tests(
                test_dir,
                pattern=args.pattern,
                verbosity=verbosity,
                failfast=args.failfast,
            )

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\nTest run interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
