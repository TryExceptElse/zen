#include <vector>
#include <string>

namespace sample {


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;
 private:
  std::vector<int> numbers_;
};

/**
 * Irrelevant, unused function definition.
 */
inline std::string RedHerring() {
  return "Cut down the tallest tree in the forest.";
}

}  // namespace sample
